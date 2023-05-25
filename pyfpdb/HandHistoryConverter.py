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
# 
from __future__ import print_function
from __future__ import division


from past.utils import old_div
#import L10n
#_ = L10n.get_translation()

import re
import sys
import traceback
from optparse import OptionParser
import os
import os.path
import xml.dom.minidom
import codecs
from decimal_wrapper import Decimal
import operator
from xml.dom.minidom import Node

import time
import datetime

from pytz import timezone
import pytz

import logging
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("parser")


import Hand
from Exceptions import *
import Configuration



class HandHistoryConverter(object):
    """
    Converts hand history files to other formats.
    """

    READ_CHUNK_SIZE = 10000 # bytes to read at a time from file in tail mode

    # filetype can be "text" or "xml"
    # so far always "text"
    # subclass HHC_xml for xml parsing
    filetype = "text"

    # codepage indicates the encoding of the text file.
    # cp1252 is a safe default
    # "utf_8" is more likely if there are funny characters
    codepage = "cp1252"

    re_tzOffset = re.compile('^\w+[+-]\d{4}$')

    copyGameHeader = False # Set to True to copy the game header to the output file.

    summaryInFile  = False # Set to True if the summary should be appended to the output file.




    # maybe archive params should be one archive param, then call method in specific converter.   if archive:  convert_archive()
    def __init__(self, config, in_path='-', out_path='-', index=0, autostart=True, starsArchive=False, ftpArchive=False, sitename="PokerStars"):
        """Initializes HandHistory object.

        Args:
            config: Configuration object.
            in_path: Input file path. Default is '-' which represents sys.stdin.
            out_path: Output file path. Default is '-' which represents sys.stdout.
            index: Index of the object.
            autostart: Boolean value indicating whether to start the object automatically.
            starsArchive: Boolean value indicating whether to archive stars.
            ftpArchive: Boolean value indicating whether to archive ftp.
            sitename: Name of the site.
        """

        self.config = config
        self.import_parameters = self.config.get_import_parameters()
        self.sitename = sitename

        # Log HandHistory initialization details.
        log.info("HandHistory init - %s site, %s subclass, in_path '%r'; out_path '%r'"
                % (self.sitename, self.__class__, in_path, out_path)) # should use self.filter, not self.sitename

        self.index = index
        self.starsArchive = starsArchive
        self.ftpArchive = ftpArchive

        self.in_path = in_path
        self.base_name = self.getBasename()
        self.out_path = out_path
        self.kodec = None

        self.processedHands = []
        self.numHands = 0
        self.numErrors = 0
        self.numPartial = 0
        self.isCarraige = False
        self.autoPop = False

        # Tourney object used to store TourneyInfo when called to deal with a Summary file.
        self.tourney = None

        if in_path == '-':
            self.in_fh = sys.stdin
        self.out_fh = get_out_fh(out_path, self.import_parameters)

        self.compiledPlayers = set()
        self.maxseats = 0

        self.status = True

        # default behaviour : parsing HH files, can be "Summary" if the parsing encounters a Summary File.
        self.parsedObjectType = "HH"

        if autostart:
            self.start()


    def __str__(self):
        """
        Converts a hand history file from a poker site into a standardized format.

        Returns:
            A string containing information about the converter's configuration.
        """
        # Use string interpolation to create a formatted string containing the converter's configuration.
        return """
        HandHistoryConverter: '%(sitename)s'  
        filetype    '%(filetype)s'
        in_path     '%(in_path)s'
        out_path    '%(out_path)s'
        """ % locals()


    def start(self):
        """Process a hand at a time from the input specified by in_path."""
        starttime = time.time()
        # Perform sanity check
        if not self.sanityCheck():
            log.warning(("Failed sanity check"))
            return

        # Initialize variables
        self.numHands = 0
        self.numPartial = 0
        self.numSkipped = 0
        self.numErrors = 0
        lastParsed = None
        handsList = self.allHandsAsList()

        # Log hands list
        log.debug(f"Hands list is:{str(handsList)}")

        # Determine if we're dealing with a HH file or a Summary file
        # quick fix : empty files make the handsList[0] fail ==> If empty file, go on with HH parsing
        if len(list(handsList)) == 0 or self.isSummary(handsList[0]) == False:
            self.parsedObjectType = "HH"
            # Loop through hands in handsList
            for handText in handsList:
                try:
                    # Process hand and append to processedHands list
                    self.processedHands.append(self.processHand(handText))
                    lastParsed = 'stored'
                except FpdbHandPartial as e:
                    # Handle partial hand exception
                    self.numPartial += 1
                    lastParsed = 'partial'
                    log.debug("%s" % e)
                except FpdbHandSkipped as e:
                    # Handle skipped hand exception
                    self.numSkipped += 1
                    lastParsed = 'skipped'
                except FpdbParseError:
                    # Handle parse error exception
                    self.numErrors += 1
                    lastParsed = 'error'
                    log.error(("FpdbParseError for file '%s'") % self.in_path)
            # Check if last hand was partially written and autoPop is enabled
            if lastParsed in ('partial', 'error') and self.autoPop:
                self.index -= len(handsList[-1])
                if self.isCarraige:
                    self.index -= handsList[-1].count('\n')
                handsList.pop()
                if lastParsed=='partial':
                    self.numPartial -= 1
                else:
                    self.numErrors -= 1
                log.info(("Removing partially written hand & resetting index"))

            # Set numHands
            self.numHands = len(list(handsList))
            endtime = time.time()

            # Log successful read of hands
            log.info(("Read %d hands (%d failed) in %.3f seconds") % (self.numHands, (self.numErrors + self.numPartial), endtime - starttime))
        else:
            self.parsedObjectType = "Summary"
            # Attempt to read summary info
            summaryParsingStatus = self.readSummaryInfo(handsList)
            endtime = time.time()
            # Log success/failure of summary file parsing
            if summaryParsingStatus :
                log.info(("Summary file '%s' correctly parsed (took %.3f seconds)") % (self.in_path, endtime - starttime))
            else :
                log.warning(("Error converting summary file '%s' (took %.3f seconds)") % (self.in_path, endtime - starttime))

    def setAutoPop(self, value):
        """
        Set the value of autoPop attribute.

        Args:
            value (bool): The value to set autoPop to.
        """
        # Set the autoPop attribute to the given value.
        self.autoPop = value

                
    def allHandsAsList(self):
        """
        Return a list of handtexts in the file at self.in_path.
        """
        # Read the file
        self.readFile()

        # Remove trailing whitespace
        lenobs = len(self.obs)
        self.obs = self.obs.rstrip()

        # Update index to reflect changes made to obs
        self.index -= (lenobs - len(self.obs))

        # Remove leading whitespace
        self.obs = self.obs.lstrip()

        # Replace carriage returns and non-breaking spaces
        self.obs = self.obs.replace('\r\n', '\n').replace(u'\xa0', u' ')

        # Check if obs length changed after replacing carriage returns and non-breaking spaces
        if lenobs != len(self.obs):
            self.isCarraige = True

        # Remove stars archive if specified
        if self.starsArchive == True:
            m = re.compile('^Hand #\d+', re.MULTILINE)
            self.obs = m.sub('', self.obs)

        # Remove ftp archive if specified
        if self.ftpArchive == True:
            m = re.compile('\*{20}\s#\s\d+\s\*{20,25}\s+', re.MULTILINE)
            self.obs = m.sub('', self.obs)

        # If obs is empty, return empty list
        if self.obs is None or self.obs == "":
            log.info(f"Read no hands from file: '{self.in_path}'")
            return []

        # Split obs into handlist using regex
        handlist = re.split(self.re_SplitHands,  self.obs)

        # Remove dangling text if less than 50 characters and log warning
        if len(handlist[-1]) <= 50:
            self.index -= len(handlist[-1])
            if self.isCarraige:
                self.index -= handlist[-1].count('\n')
            handlist.pop()
            log.info(("Removing text < 50 characters & resetting index"))

        # Return handlist
        return handlist


    def processHand(self, handText):
        """
        Process a hand of text and return a Hand object.

        Parameters:
            handText (str): The text of the hand to be processed.

        Returns:
            Hand: The processed Hand object.

        Raises:
            FpdbHandPartial: If the handText is partial and cannot be identified as a hand.
            FpdbHandSkipped: If the gametype of the hand is in the importFilters and should be skipped.
            FpdbParseError: If the gametype of the hand is not supported.
        """

        # Check if handText is partial and raise an exception if it is.
        if self.isPartial(handText):
            raise FpdbHandPartial(f"Could not identify as a {self.sitename} hand")

        # Parse the gametype of the hand.
        if self.copyGameHeader:
            gametype = self.parseHeader(handText, self.whole_file.replace('\r\n', '\n').replace(u'\xa0', u' '))
        else:
            gametype = self.determineGameType(handText)

        # Initialize variables.
        hand = None
        l = None

        # If the gametype cannot be determined, set it to "unmatched" and increment numErrors.
        if gametype is None:
            gametype = "unmatched"
            # TODO: not ideal, just trying to not error. Throw ParseException?
            self.numErrors += 1
        else:
            print(gametype)
            print('gametypecategory',gametype['category'])
            # If the gametype is in the importFilters, skip it.
            if gametype['category'] in self.import_parameters['importFilters']:
                raise FpdbHandSkipped("Skipped %s hand" % gametype['type'])
            # Set default values for gametype parameters.
            if 'mix' not in gametype: gametype['mix'] = 'none'
            if 'ante' not in gametype: gametype['ante'] = 0
            if 'buyinType' not in gametype: gametype['buyinType'] = 'regular'
            if 'fast' not in gametype: gametype['fast'] = False
            if 'newToGame' not in gametype: gametype['newToGame'] = False
            if 'homeGame' not in gametype: gametype['homeGame'] = False
            if 'split' not in gametype: gametype['split'] = False
            type = gametype['type']
            base = gametype['base']
            limit = gametype['limitType']
            l = [type] + [base] + [limit]

        # Check if the gametype is supported and create a Hand object if it is.
        if l in self.readSupportedGames():
            if gametype['base'] == 'hold':
                hand = Hand.HoldemOmahaHand(self.config, self, self.sitename, gametype, handText)
            elif gametype['base'] == 'stud':
                hand = Hand.StudHand(self.config, self, self.sitename, gametype, handText)
            elif gametype['base'] == 'draw':
                hand = Hand.DrawHand(self.config, self, self.sitename, gametype, handText)
        else:
            log.error(f"{self.sitename} Unsupported game type: {gametype}")
            raise FpdbParseError

        # Write the Hand object and return it.
        if hand:
            #hand.writeHand(self.out_fh)
            return hand
        else:
            log.error(f"{self.sitename} Unsupported game type: {gametype}")
            # TODO: pity we don't know the HID at this stage.

            

    def isPartial(self, handText):
        """
        Returns whether the given handText contains multiple parts or not.

        Args:
            handText (str): The text to be checked.

        Returns:
            bool: True if the text contains multiple parts, False otherwise.
        """
        # Count the number of parts in the handText using a regular expression.
        count = sum(1 for _ in self.re_Identify.finditer(handText))
        # Return True if the count is not equal to 1, indicating there are multiple parts.
        return count != 1

    
    # These functions are parse actions that may be overridden by the inheriting class
    # This function should return a list of lists looking like:
    # return [["ring", "hold", "nl"], ["tour", "hold", "nl"]]
    # Showing all supported games limits and types

    def readSupportedGames(self): abstract

    # should return a list
    #   type  base limit
    # [ ring, hold, nl   , sb, bb ]
    # Valid types specified in docs/tabledesign.html in Gametypes
    
    
    def determineGameType(self, handText): abstract
    """return dict with keys/values:
    'type'       in ('ring', 'tour')
    'limitType'  in ('nl', 'cn', 'pl', 'cp', 'fl')
    'base'       in ('hold', 'stud', 'draw')
    'category'   in ('holdem', 'omahahi', omahahilo', 'fusion', 'razz', 'studhi', 'studhilo', 'fivedraw', '27_1draw', '27_3draw', 'badugi')
    'hilo'       in ('h','l','s')
    'mix'        in (site specific, or 'none')
    'smallBlind' int?
    'bigBlind'   int?
    'smallBet'
    'bigBet'
    'currency'  in ('USD', 'EUR', 'T$', <countrycode>)
or None if we fail to get the info """
    #TODO: which parts are optional/required?

    def readHandInfo(self, hand): abstract
    """Read and set information about the hand being dealt, and set the correct 
    variables in the Hand object 'hand

    * hand.startTime - a datetime object
    * hand.handid - The site identified for the hand - a string.
    * hand.tablename
    * hand.buttonpos
    * hand.maxseats
    * hand.mixed

    Tournament fields:

    * hand.tourNo - The site identified tournament id as appropriate - a string.
    * hand.buyin
    * hand.fee
    * hand.buyinCurrency
    * hand.koBounty
    * hand.isKO
    * hand.level
    """
    #TODO: which parts are optional/required?

    def readPlayerStacks(self, hand): abstract
    """This function is for identifying players at the table, and to pass the 
    information on to 'hand' via Hand.addPlayer(seat, name, chips)

    At the time of writing the reference function in the PS converter is:
        log.debug("readPlayerStacks")
        m = self.re_PlayerInfo.finditer(hand.handText)
        for a in m:
            hand.addPlayer(int(a.group('SEAT')), a.group('PNAME'), a.group('CASH'))

    Which is pretty simple because the hand history format is consistent. Other hh formats aren't so nice.

    This is the appropriate place to identify players that are sitting out and ignore them

    *** NOTE: You may find this is a more appropriate place to set hand.maxseats ***
    """

    def compilePlayerRegexs(self): abstract
    """Compile dynamic regexes -- compile player dependent regexes.

    Depending on the ambiguity of lines you may need to match, and the complexity of 
    player names - we found that we needed to recompile some regexes for player actions so that they actually contained the player names.

    eg.
    We need to match the ante line:
    <Player> antes $1.00

    But <Player> is actually named

    YesI antes $4000 - A perfectly legal playername

    Giving:

    YesI antes $4000 antes $1.00

    Which without care in your regexes most people would match 'YesI' and not 'YesI antes $4000'
    """

    # Needs to return a MatchObject with group names identifying the streets into the Hand object
    # so groups are called by street names 'PREFLOP', 'FLOP', 'STREET2' etc
    # blinds are done seperately
    def markStreets(self, hand): abstract
    """For dividing the handText into sections.

    The function requires you to pass a MatchObject with groups specifically labeled with
    the 'correct' street names.

    The Hand object will use the various matches for assigning actions to the correct streets.

    Flop Based Games:
    PREFLOP, FLOP, TURN, RIVER

    Draw Based Games:
    PREDEAL, DEAL, DRAWONE, DRAWTWO, DRAWTHREE

    Stud Based Games:
    ANTES, THIRD, FOURTH, FIFTH, SIXTH, SEVENTH

    The Stars HHC has a good reference implementation
    """

    #Needs to return a list in the format
    # ['player1name', 'player2name', ...] where player1name is the sb and player2name is bb,
    # addtional players are assumed to post a bb oop
    def readBlinds(self, hand): abstract
    """Function for reading the various blinds from the hand history.

    Pass any small blind to hand.addBlind(<name>, "small blind", <value>)
    - unless it is a single dead small blind then use:
        hand.addBlind(<name>, 'secondsb', <value>)
    Pass any big blind to hand.addBlind(<name>, "big blind", <value>)
    Pass any play posting both big and small blinds to hand.addBlind(<name>, 'both', <vale>)
    """
    def readSTP(self, hand): pass
    
    def readAntes(self, hand): abstract
    """Function for reading the antes from the hand history and passing the hand.addAnte"""
    def readBringIn(self, hand): abstract
    
    def readButton(self, hand): abstract
    
    def readHoleCards(self, hand): abstract
    
    def readAction(self, hand, street): abstract
    
    def readCollectPot(self, hand): abstract
    
    def readShownCards(self, hand): abstract
    
    def readTourneyResults(self, hand): 
        """This function is for future use in parsing tourney results directly from a hand"""
        pass
    
    # EDIT: readOther is depreciated
    # Some sites do odd stuff that doesn't fall in to the normal HH parsing.
    # e.g., FTP doesn't put mixed game info in the HH, but puts in in the
    # file name. Use readOther() to clean up those messes.
    def readOther(self, hand): pass

    # Some sites don't report the rake. This will be called at the end of the hand after the pot total has been calculated
    # an inheriting class can calculate it for the specific site if need be.
    def getRake(self, hand):
        """
        Calculates the rake for a given hand object.

        Args:
            hand: A hand object representing the hand being played.

        Raises:
            FpdbParseError: If an error occurs when calculating the rake.

        Returns:
            None
        """
        # Print total pot
        print('total pot', hand.totalpot)
        # Print collected pot
        print('collected pot', hand.totalcollected)

        # Check if collected pot is greater than total pot
        if hand.totalcollected > hand.totalpot:
            print("collected pot>total pot")

        # Calculate rake
        hand.rake = hand.totalpot - hand.totalcollected  # * Decimal('0.05') # probably not quite right

        # Determine round value based on game type and site ID
        if self.siteId == 9 and hand.gametype['type'] == "tour":
            round = -5  # round up to 10
        elif hand.gametype['type'] == "tour":
            round = -1
        else:
            round = -0.01

        # Adjust rake for site ID 15 and total collected greater than total pot
        if self.siteId == 15 and hand.totalcollected > hand.totalpot:
            hand.rake = old_div(hand.totalpot, 10)
            print(hand.rake)

        # Check if rake is negative and if it meets the round value criteria
        if hand.rake < 0 and (not hand.roundPenny or hand.rake < round) and not hand.cashedOut:
            if (self.siteId == 28 and
                    ((hand.rake + Decimal(str(hand.sb)) - (0 if hand.rakes.get('rake') is None else hand.rakes['rake'])) == 0 or
                    (hand.rake + Decimal(str(hand.sb)) + Decimal(str(hand.bb)) - (0 if hand.rakes.get('rake') is None else hand.rakes['rake'])) == 0)
            ):
                # Log error if missed sb/bb
                log.error(
                    f"hhc.getRake(): '{hand.handid}': Missed sb/bb - Amount collected ({str(hand.totalcollected)}) is greater than the pot ({str(hand.totalpot)})"
                )
            else:
                # Log error if collected pot is greater than total pot
                log.error(
                    f"hhc.getRake(): '{hand.handid}': Amount collected ({str(hand.totalcollected)}) is greater than the pot ({str(hand.totalpot)})"
                )
                raise FpdbParseError

        # Check if rake is suspiciously high
        elif hand.totalpot > 0 and Decimal(old_div(hand.totalpot, 4)) < hand.rake and not hand.fastFold and not hand.cashedOut:
            log.error(
                f"hhc.getRake(): '{hand.handid}': Suspiciously high rake ({str(hand.rake)}) > 25 pct of pot ({str(hand.totalpot)})"
            )
            raise FpdbParseError


    def sanityCheck(self):
        """
        Check if the program is in a sane state.
        Returns a boolean indicating whether the program is sane or not.
        """
        # Initially we assume the program is sane.
        sane = True

        # Check if the input and output files are the same.
        if self.in_path != '-' and self.out_path == self.in_path:
            print("Output and input files are the same, check config.")
            sane = False

        return sane


    # Functions not necessary to implement in sub class
    def setFileType(self, filetype = "text", codepage='utf8'):
        """
        Sets the file type and code page for the current object instance.

        Args:
            filetype (str): The file type to set (default is "text").
            codepage (str): The code page to set (default is "utf8").
        """
        self.filetype = filetype
        self.codepage = codepage
        
    # Import from string
    def setObs(self, text):
        """Set the observation and update the whole file.

        Args:
            text (str): The new observation to set.
        """
        self.obs = text
        self.whole_file = text

    def __listof(self, x):
        """
        Converts the input to a list if it's not already a list or tuple.

        Args:
            x: object

        Returns:
            list: Returns the input as a list if it's not already a list or tuple, otherwise returns the input.
        """
        return x if isinstance(x, (list, tuple)) else [x]

    def readFile(self):
        """
        Open in_path according to self.codepage. Exceptions caught further up

        Returns:
        - True if file was read successfully
        - False otherwise
        """

        if self.filetype == "text":
            # Try to open the file with each kodec in self.__listof(self.codepage)
            for kodec in self.__listof(self.codepage):
                try:
                    in_fh = codecs.open(self.in_path, 'r', kodec)
                    self.whole_file = in_fh.read()
                    in_fh.close()
                    self.obs = self.whole_file[self.index:]
                    self.index = len(self.whole_file)
                    self.kodec = kodec
                    return True
                except Exception:
                    pass
            # If all koceds fail, log an error and return False
            log.error(("unable to read file with any codec in list!") + " " + self.in_path)
            self.obs = ""
            return False
        elif self.filetype == "xml":
            # Parse the xml file and store it in self.doc
            doc = xml.dom.minidom.parse(filename)
            self.doc = doc
        elif self.filetype == "":
            # Do nothing if filetype is not specified
            pass


    def guessMaxSeats(self, hand):
        """
        Return a guess at max seats when not specified in HH.
        If some other code prior to this has already set it, return it.

        Args:
            hand: An instance of the Hand class.

        Returns:
            An integer representing the guessed max seats.
        """

        # if some other code prior to this has already set it, return it
        if not self.copyGameHeader and hand.gametype['type'] == 'tour':
            return 10

        # If maxseats is already set, return it.
        if self.maxseats > 1 and self.maxseats < 11:
            return self.maxseats

        # Get the maximum occurrences of a seat
        mo = self.maxOccSeat(hand)

        # If the max occurrences is already 10, return 10
        if mo == 10:
            return 10

        # If the game type is stud and the max occurrences is less than or equal to 8, return 8
        if hand.gametype['base'] == 'stud' and mo <= 8:
            return 8

        # If the game type is draw and the max occurrences is less than or equal to 6, return 6, else return 10
        return 6 if hand.gametype['base'] == 'draw' and mo <= 6 else 10

    def maxOccSeat(self, hand):
        """
        Finds the maximum occurrence of a seat number in the given hand.

        Args:
            hand (Hand): The hand to search for the maximum occurrence of seat numbers.

        Returns:
            int: The maximum occurrence of a seat number in the hand.
        """
        max = 0  # initialize the maximum occurrence to 0
        for player in hand.players:
            if int(player[0]) > max:
                max = int(player[0])  # update the maximum occurrence if necessary
        return max  # return the maximum occurrence


    def getStatus(self):
        """
        Returns the status of the file processing.

        :return: True if file processed successfully, False otherwise.
        """
        # TODO: Return a status of true if file processed ok
        return self.status

    def getProcessedHands(self):
        """Returns the processed hands."""
        return self.processedHands # returns the processed hands


    def getProcessedFile(self):
        """
        Returns the output file path
        """
        return self.out_path

    def getLastCharacterRead(self):
        """
        Returns the index of the last character read.
        """
        return self.index

    def isSummary(self, topline):
        """
        Check if the given string is a summary of a tournament report.

        Args:
            topline (str): The first line of the tournament report.

        Returns:
            bool: True if the given string is a summary of a tournament report, False otherwise.
        """
        return " Tournament Summary " in topline

    def getParsedObjectType(self):
        """Gets the parsed object type.

        Returns:
            The parsed object type.
        """
        return self.parsedObjectType

    def getBasename(self):
        """
        Get the basename of the file without the extension.

        Returns:
            str: The basename of the file without the extension.
        """
        head, tail = os.path.split(self.in_path)
        base = tail or os.path.basename(head)
        return base.split('.')[0]

    #returns a status (True/False) indicating wether the parsing could be done correctly or not
    def readSummaryInfo(self, summaryInfoList): abstract

    def getTourney(self):
        """
        Gets the tourney.

        :return: The tourney.
        """
        return self.tourney
        
    @staticmethod
    def changeTimezone(time, givenTimezone, wantedTimezone):
        """Takes a givenTimezone in format AAA or AAA+HHMM where AAA is a standard timezone
           and +HHMM is an optional offset (+/-) in hours (HH) and minutes (MM)
           (See OnGameToFpdb.py for example use of the +HHMM part)
           Tries to convert the time parameter (with no timezone) from the givenTimezone to 
           the wantedTimeZone (currently only allows "UTC")
        """
        #log.debug("raw time: " + str(time) + " given time zone: " + str(givenTimezone))
        if wantedTimezone=="UTC":
            wantedTimezone = pytz.utc
        else:
            log.error(f"Unsupported target timezone: {givenTimezone}")
            raise FpdbParseError(f"Unsupported target timezone: {givenTimezone}")

        givenTZ = None
        if HandHistoryConverter.re_tzOffset.match(givenTimezone):
            offset = int(givenTimezone[-5:])
            givenTimezone = givenTimezone[:-5]
                #log.debug("changeTimeZone: offset=" + str(offset))
        else: offset=0

        if givenTimezone in ("ET", "EST", "EDT"):
            givenTZ = timezone('US/Eastern')
        elif givenTimezone in ("CET", "CEST", "MEZ", "MESZ", "HAEC"):
            #since CEST will only be used in summer time it's ok to treat it as identical to CET.
            givenTZ = timezone('Europe/Berlin')
            #Note: Daylight Saving Time is standardised across the EU so this should be fine
        elif givenTimezone in ('GT', 'GMT'): # GMT is always the same as UTC
            givenTZ = timezone('GMT')
            # GMT cannot be treated as WET because some HH's are explicitly
            # GMT+-delta so would be incorrect during the summertime 
            # if substituted as WET+-delta
        elif givenTimezone == 'BST':
             givenTZ = timezone('Europe/London')
        elif givenTimezone == 'WET': # WET is GMT with daylight saving delta
            givenTZ = timezone('WET')
        elif givenTimezone in ('HT', 'HST', 'HDT'): # Hawaiian Standard Time
            givenTZ = timezone('US/Hawaii')
        elif givenTimezone == 'AKT': # Alaska Time
            givenTZ = timezone('US/Alaska')
        elif givenTimezone in ('PT', 'PST', 'PDT'): # Pacific Time
            givenTZ = timezone('US/Pacific')
        elif givenTimezone in ('MT', 'MST', 'MDT'): # Mountain Time
            givenTZ = timezone('US/Mountain')
        elif givenTimezone in ('CT', 'CST', 'CDT'): # Central Time
            givenTZ = timezone('US/Central')
        elif givenTimezone == 'AT': # Atlantic Time
            givenTZ = timezone('Canada/Atlantic')
        elif givenTimezone == 'NT': # Newfoundland Time
            givenTZ = timezone('Canada/Newfoundland')
        elif givenTimezone == 'ART': # Argentinian Time
            givenTZ = timezone('America/Argentina/Buenos_Aires')
        elif givenTimezone in ('BRT', 'BRST'): # Brasilia Time
            givenTZ = timezone('America/Sao_Paulo')
        elif givenTimezone == 'VET':
            givenTZ = timezone('America/Caracas')
        elif givenTimezone == 'COT':
            givenTZ = timezone('America/Bogota')
        elif givenTimezone in ('EET', 'EEST'): # Eastern European Time
            givenTZ = timezone('Europe/Bucharest')
        elif givenTimezone in ('MSK', 'MESZ', 'MSKS', 'MSD'): # Moscow Standard Time
            givenTZ = timezone('Europe/Moscow')
        elif givenTimezone == 'GST':
            givenTZ = timezone('Asia/Dubai')
        elif givenTimezone in ('YEKT','YEKST'):
            givenTZ = timezone('Asia/Yekaterinburg')
        elif givenTimezone in ('KRAT','KRAST'):
            givenTZ = timezone('Asia/Krasnoyarsk')
        elif givenTimezone == 'IST': # India Standard Time
            givenTZ = timezone('Asia/Kolkata')
        elif givenTimezone == 'ICT':
            givenTZ = timezone('Asia/Bangkok')
        elif givenTimezone == 'CCT': # China Coast Time
            givenTZ = timezone('Australia/West')
        elif givenTimezone == 'JST': # Japan Standard Time
            givenTZ = timezone('Asia/Tokyo')
        elif givenTimezone in ('AWST', 'AWT'):  # Australian Western Standard Time
            givenTZ = timezone('Australia/West')
        elif givenTimezone in ('ACST', 'ACT'): # Australian Central Standard Time
            givenTZ = timezone('Australia/Darwin')
        elif givenTimezone in ('AEST', 'AET'): # Australian Eastern Standard Time
            # Each State on the East Coast has different DSTs.
            # Melbournce is out because I don't like AFL, Queensland doesn't have DST
            # ACT is full of politicians and Tasmania will never notice.
            # Using Sydney. 
            givenTZ = timezone('Australia/Sydney')
        elif givenTimezone in ('NZST', 'NZT', 'NZDT'): # New Zealand Time
            givenTZ = timezone('Pacific/Auckland')
        elif givenTimezone == 'UTC': # Universal time co-ordinated
            givenTZ = pytz.UTC
        elif givenTimezone in pytz.all_timezones:
            givenTZ = timezone(givenTimezone)
        else:
            timezone_lookup = dict([(pytz.timezone(x).localize(datetime.datetime.now()).tzname(), x) for x in pytz.all_timezones])
            if givenTimezone in timezone_lookup:
                givenTZ = timezone(timezone_lookup[givenTimezone])

        if givenTZ is None:
            # do not crash if timezone not in list, just return UTC localized time
            log.error(("Timezone conversion not supported") + ": " + givenTimezone + " " + str(time))
            givenTZ = pytz.UTC
            return givenTZ.localize(time)

        localisedTime = givenTZ.localize(time)
        return localisedTime.astimezone(wantedTimezone) + datetime.timedelta(
            seconds=-3600 * (old_div(offset, 100)) - 60 * (offset % 100)
        )
    #end @staticmethod def changeTimezone

    @staticmethod
    def getTableTitleRe(type, table_name=None, tournament=None, table_number=None):
        """Returns a regex string to search in window titles.

        Args:
            type (str): Type of regex string to return. Either "tour" or anything else.
            table_name (str, optional): Name of the table. Defaults to None.
            tournament (str, optional): Name of the tournament. Defaults to None.
            table_number (int, optional): Number of the table. Defaults to None.

        Returns:
            str: Regex string to search in window titles.
        """
        if type == "tour":
            # If type is "tour", return a regex string that matches the tournament name,
            # any characters in between, the word "Table", and the table number.
            return (re.escape(str(tournament)) + ".+\\Table " + re.escape(str(table_number)))
        else:
            # If type is anything else, return the escaped table name.
            return re.escape(table_name)

    @staticmethod
    def getTableNoRe(tournament):
        """
        Returns a regular expression pattern that matches the table number in a tournament window title.
        :param tournament: The name of the tournament.
        :return: A regular expression pattern that matches the table number in a tournament window title.
        """
        # Example window titles:
        # Full Tilt:  $30 + $3 Tournament (181398949), Table 1 - 600/1200 Ante 100 - Limit Razz
        # PokerStars: WCOOP 2nd Chance 02: $1,050 NLHE - Tournament 307521826 Table 1 - Blinds $30/$60

        # The regular expression pattern matches the tournament name followed by "Table" or "Torneo", followed by one or more digits.
        return "%s.+(?:Table|Torneo) (\d+)" % (tournament, )


    @staticmethod
    def clearMoneyString(money):
        """Converts human readable string representations of numbers like
        '1 200', '2,000', '0,01' to more machine processable form - no commas, 1 decimal point
        """
        if not money:
            return money
        money = money.replace(' ', '')
        money = money.replace(u'\xa0', u'')
        if 'K' in money:
            money = money.replace('K', '000')
        if 'M' in money:
            money = money.replace('M', '000000')
        if 'B' in money:
            money = money.replace('B', '000000000')
        if money[-1] in ('.', ','):
            money = money[:-1]
        if len(money) < 3:
            return money # No commas until 0,01 or 1,00
        if money[-3] == ',':
            money = f'{money[:-3]}.{money[-2:]}'
            if len(money) > 15 and money[-15] == '.':
                money = f'{money[:-15]},{money[-14:]}'
            if len(money) > 11 and money[-11] == '.':
                money = f'{money[:-11]},{money[-10:]}'
            if len(money) > 7 and money[-7] == '.':
                money = f'{money[:-7]},{money[-6:]}'
        else:
            if len(money) > 12 and money[-12] == '.':
                money = f'{money[:-12]},{money[-11:]}'
            if len(money) > 8 and money[-8] == '.':
                money = f'{money[:-8]},{money[-7:]}'
            if len(money) > 4 and money[-4] == '.':
                money = f'{money[:-4]},{money[-3:]}'
        return money.replace(',', '').replace("'", '')


def getTableTitleRe(config, sitename, *args, **kwargs):
    """
        Returns a string to search in windows titles for the current site.

        Args:
            config: Dictionary containing site configuration information.
            sitename: String representing the name of the current site.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            String to search in windows titles for current site.
    """
    # Call getTableTitleRe method of SiteHhc object returned by getSiteHhc function.
    return getSiteHhc(config, sitename).getTableTitleRe(*args, **kwargs)

def getTableNoRe(config, sitename, *args, **kwargs):
    """Returns regex string to search window titles for tournament table number.

    Args:
        config (str): Configuration string.
        sitename (str): Name of the site.
        *args: Variable length argument list.
        **kwargs: Arbitrary keyword arguments.

    Returns:
        str: Regex string to search window titles for tournament table number.
    """
    # Call getTableNoRe method of SiteHhc object returned by getSiteHhc method
    # with the given arguments and return its value
    return getSiteHhc(config, sitename).getTableNoRe(*args, **kwargs)


def getSiteHhc(config, sitename):
    """
    Returns HHC class for current site.

    Args:
        config (dict): Configuration dictionary.
        sitename (str): Name of the site.

    Returns:
        class: HHC class for the given site.
    """
    # Get the name of the HHC class converter for the given site.
    hhcName = config.hhcs[sitename].converter

    # Dynamically import the module containing the HHC class.
    hhcModule = __import__(hhcName)

    # Return the HHC class by getting the attribute from the module.
    # We remove the last 6 characters from the name to get the class name.
    return getattr(hhcModule, hhcName[:-6])



def get_out_fh(out_path, parameters):
    """
    Returns file handle for output file.

    Args:
        out_path (str): Path to output file.
        parameters (dict): A dictionary of parameters.

    Returns:
        file handle: A file handle for the output file.
    """
    # If output path is '-' or saveStarsHH is False return stdout
    if out_path == '-' or not parameters['saveStarsHH']:
        return sys.stdout

    # Create output directory if it doesn't exist
    out_dir = os.path.dirname(out_path)
    if not os.path.isdir(out_dir) and out_dir != '':
        try:
            os.makedirs(out_dir)
        except Exception:
            log.error(f"Unable to create output directory {out_dir} for HHC!")
        else:
            log.info(f"Created directory '{out_dir}'")

    # Try to open the output file
    try:
        return codecs.open(out_path, 'w', 'utf8')
    except Exception:
        log.error(f"Output path {out_path} couldn't be opened.")
