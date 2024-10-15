#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2008-2011 Carl Gherardi
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
from __future__ import print_function
from __future__ import division


from past.utils import old_div
# import L10n
# _ = L10n.get_translation()

import re
import sys
import os
import os.path
import xml.dom.minidom
import codecs
from decimal import Decimal

import time
import datetime

from pytz import timezone
import pytz

import logging


import Hand
from Exceptions import FpdbParseError, FpdbHandPartial, FpdbHandSkipped
from abc import ABC, abstractmethod

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("handHistoryConverter")


class HandHistoryConverter(ABC):
    READ_CHUNK_SIZE = 10000  # bytes to read at a time from file in tail mode

    # filetype can be "text" or "xml"
    # so far always "text"
    # subclass HHC_xml for xml parsing
    filetype = "text"

    # codepage indicates the encoding of the text file.
    # cp1252 is a safe default
    # "utf_8" is more likely if there are funny characters
    codepage = "cp1252"

    re_tzOffset = re.compile("^\w+[+-]\d{4}$")
    copyGameHeader = False
    summaryInFile = False

    # maybe archive params should be one archive param, then call method in specific converter.   if archive:  convert_archive()
    def __init__(
        self,
        config,
        in_path="-",
        out_path="-",
        index=0,
        autostart=True,
        starsArchive=False,
        ftpArchive=False,
        sitename="PokerStars",
    ):
        """\
in_path   (default '-' = sys.stdin)
out_path  (default '-' = sys.stdout)
"""

        self.config = config
        self.import_parameters = self.config.get_import_parameters()
        self.sitename = sitename
        log.info(
            "HandHistory init - %s site, %s subclass, in_path '%r'; out_path '%r'"
            % (self.sitename, self.__class__, in_path, out_path)
        )  # should use self.filter, not self.sitename

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

        # Tourney object used to store TourneyInfo when called to deal with a Summary file
        self.tourney = None

        if in_path == "-":
            self.in_fh = sys.stdin
        self.out_fh = get_out_fh(out_path, self.import_parameters)

        self.compiledPlayers = set()
        self.maxseats = 0

        self.status = True

        self.parsedObjectType = (
            "HH"  # default behaviour : parsing HH files, can be "Summary" if the parsing encounters a Summary File
        )

        if autostart:
            self.start()

    def __str__(self):
        return """
HandHistoryConverter: '%(sitename)s'  
    filetype    '%(filetype)s'
    in_path     '%(in_path)s'
    out_path    '%(out_path)s'
    """ % locals()

    def start(self):
        """Process a hand at a time from the input specified by in_path."""
        starttime = time.time()
        if not self.sanityCheck():
            log.warning(("Failed sanity check"))
            return

        self.numHands = 0
        self.numPartial = 0
        self.numSkipped = 0
        self.numErrors = 0
        lastParsed = None
        handsList = self.allHandsAsList()
        log.debug(("Hands list is:") + str(handsList))
        log.info(("Parsing %d hands") % len(list(handsList)))
        # Determine if we're dealing with a HH file or a Summary file
        # quick fix : empty files make the handsList[0] fail ==> If empty file, go on with HH parsing
        if len(list(handsList)) == 0 or self.isSummary(handsList[0]) is False:
            self.parsedObjectType = "HH"
            for handText in handsList:
                try:
                    self.processedHands.append(self.processHand(handText))
                    lastParsed = "stored"
                except FpdbHandPartial as e:
                    self.numPartial += 1
                    lastParsed = "partial"
                    log.debug("%s" % e)
                except FpdbHandSkipped:
                    self.numSkipped += 1
                    lastParsed = "skipped"
                except FpdbParseError:
                    self.numErrors += 1
                    lastParsed = "error"
                    log.error(("FpdbParseError for file '%s'") % self.in_path)
            if lastParsed in ("partial", "error") and self.autoPop:
                self.index -= len(handsList[-1])
                if self.isCarraige:
                    self.index -= handsList[-1].count("\n")
                handsList.pop()
                if lastParsed == "partial":
                    self.numPartial -= 1
                else:
                    self.numErrors -= 1
                log.info(("Removing partially written hand & resetting index"))
            self.numHands = len(list(handsList))
            endtime = time.time()
            log.info(
                ("Read %d hands (%d failed) in %.3f seconds")
                % (self.numHands, (self.numErrors + self.numPartial), endtime - starttime)
            )
        else:
            self.parsedObjectType = "Summary"
            summaryParsingStatus = self.readSummaryInfo(handsList)
            endtime = time.time()
            if summaryParsingStatus:
                log.info(
                    ("Summary file '%s' correctly parsed (took %.3f seconds)") % (self.in_path, endtime - starttime)
                )
            else:
                log.warning(
                    ("Error converting summary file '%s' (took %.3f seconds)") % (self.in_path, endtime - starttime)
                )

    def setAutoPop(self, value):
        self.autoPop = value

    def allHandsAsList(self):
        """Return a list of handtexts in the file at self.in_path"""
        # TODO : any need for this to be generator? e.g. stars support can email one huge file of all hands in a year. Better to read bit by bit than all at once.
        self.readFile()
        lenobs = len(self.obs)
        self.obs = self.obs.rstrip()
        self.index -= lenobs - len(self.obs)
        self.obs = self.obs.lstrip()
        lenobs = len(self.obs)
        self.obs = self.obs.replace("\r\n", "\n").replace("\xa0", " ")
        if lenobs != len(self.obs):
            self.isCarraige = True
        # maybe archive params should be one archive param, then call method in specific converter?
        # if self.archive:
        #     self.obs = self.convert_archive(self.obs)
        if self.starsArchive is True:
            m = re.compile("^Hand #\d+", re.MULTILINE)
            self.obs = m.sub("", self.obs)

        if self.ftpArchive is True:
            # Remove  ******************** # 1 *************************
            m = re.compile("\*{20}\s#\s\d+\s\*{20,25}\s+", re.MULTILINE)
            self.obs = m.sub("", self.obs)

        if self.obs is None or self.obs == "":
            log.info(("Read no hands from file: '%s'") % self.in_path)
            return []
        handlist = re.split(self.re_SplitHands, self.obs)
        # Some HH formats leave dangling text after the split
        # ie. </game> (split) </session>EOL
        # Remove this dangler if less than 50 characters and warn in the log
        if len(handlist[-1]) <= 50:
            self.index -= len(handlist[-1])
            if self.isCarraige:
                self.index -= handlist[-1].count("\n")
            handlist.pop()
            log.info(("Removing text < 50 characters & resetting index"))
        return handlist

    def processHand(self, handText):
        if self.isPartial(handText):
            raise FpdbHandPartial("Could not identify as a %s hand" % self.sitename)

        if self.copyGameHeader:
            gametype = self.parseHeader(handText, self.whole_file.replace("\r\n", "\n").replace("\xa0", " "))
        else:
            gametype = self.determineGameType(handText)

        hand = None
        game_details = None

        if gametype is None:
            gametype = "unmatched"
            # TODO: not ideal, just trying to not error. Throw ParseException?
            self.numErrors += 1
        else:
            print(gametype)
            print("gametypecategory", gametype["category"])
            if gametype["category"] in self.import_parameters["importFilters"]:
                raise FpdbHandSkipped("Skipped %s hand" % gametype["type"])

            # Ensure game type has all necessary attributes
            gametype.setdefault("mix", "none")
            gametype.setdefault("ante", 0)
            gametype.setdefault("buyinType", "regular")
            gametype.setdefault("fast", False)
            gametype.setdefault("newToGame", False)
            gametype.setdefault("homeGame", False)
            gametype.setdefault("split", False)

            type = gametype["type"]
            base = gametype["base"]
            limit = gametype["limitType"]
            game_details = [type, base, limit]

        if game_details in self.readSupportedGames():
            if gametype["base"] == "hold":
                hand = Hand.HoldemOmahaHand(self.config, self, self.sitename, gametype, handText)
            elif gametype["base"] == "stud":
                hand = Hand.StudHand(self.config, self, self.sitename, gametype, handText)
            elif gametype["base"] == "draw":
                hand = Hand.DrawHand(self.config, self, self.sitename, gametype, handText)
        else:
            log.error("%s Unsupported game type: %s", self.sitename, gametype)
            raise FpdbParseError

        if hand:
            # hand.writeHand(self.out_fh)
            return hand
        else:
            log.error("%s Unsupported game type: %s", self.sitename, gametype)
            # TODO: pity we don't know the HID at this stage. Log the entire hand?

    def isPartial(self, handText):
        count = 0
        for m in self.re_Identify.finditer(handText):
            count += 1
        if count != 1:
            return True
        return False

    # These functions are parse actions that may be overridden by the inheriting class
    # This function should return a list of lists looking like:
    # return [["ring", "hold", "nl"], ["tour", "hold", "nl"]]
    # Showing all supported games limits and types

    @abstractmethod
    def readSupportedGames(self):
        """This method must be implemented by subclasses to define supported games."""
        pass

    @abstractmethod
    def determineGameType(self, handText):
        """This method must be implemented by subclasses to define game type determination logic."""
        pass

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

    # TODO: which parts are optional/required?
    @abstractmethod
    def readHandInfo(self, hand):
        pass

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

    # TODO: which parts are optional/required?
    @abstractmethod
    def readPlayerStacks(self, hand):
        pass

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

    @abstractmethod
    def compilePlayerRegexs(self):
        pass

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
    @abstractmethod
    def markStreets(self, hand):
        pass

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

    # Needs to return a list in the format
    # ['player1name', 'player2name', ...] where player1name is the sb and player2name is bb,
    # addtional players are assumed to post a bb oop
    @abstractmethod
    def readBlinds(self, hand):
        pass

    """Function for reading the various blinds from the hand history.

    Pass any small blind to hand.addBlind(<name>, "small blind", <value>)
    - unless it is a single dead small blind then use:
        hand.addBlind(<name>, 'secondsb', <value>)
    Pass any big blind to hand.addBlind(<name>, "big blind", <value>)
    Pass any play posting both big and small blinds to hand.addBlind(<name>, 'both', <vale>)
    """

    @abstractmethod
    def readSTP(self, hand):
        pass

    @abstractmethod
    def readAntes(self, hand):
        pass

    """Function for reading the antes from the hand history and passing the hand.addAnte"""

    @abstractmethod
    def readBringIn(self, hand):
        pass

    @abstractmethod
    def readButton(self, hand):
        pass

    @abstractmethod
    def readHoleCards(self, hand):
        pass

    @abstractmethod
    def readAction(self, hand, street):
        pass

    @abstractmethod
    def readCollectPot(self, hand):
        pass

    @abstractmethod
    def readShownCards(self, hand):
        pass

    @abstractmethod
    def readTourneyResults(self, hand):
        """This function is for future use in parsing tourney results directly from a hand"""
        pass

    # EDIT: readOther is depreciated
    # Some sites do odd stuff that doesn't fall in to the normal HH parsing.
    # e.g., FTP doesn't put mixed game info in the HH, but puts in in the
    # file name. Use readOther() to clean up those messes.
    # @abstractmethod
    # def readOther(self, hand):
    #     pass

    # Some sites don't report the rake. This will be called at the end of the hand after the pot total has been calculated
    # an inheriting class can calculate it for the specific site if need be.
    def getRake(self, hand):
        print("total pot", hand.totalpot)
        print("collected pot", hand.totalcollected)
        if hand.totalcollected > hand.totalpot:
            print("collected pot>total pot")
        if hand.rake is None:
            hand.rake = hand.totalpot - hand.totalcollected  #  * Decimal('0.05') # probably not quite right
        if self.siteId == 9 and hand.gametype["type"] == "tour":
            round = -5  # round up to 10
        elif hand.gametype["type"] == "tour":
            round = -1
        else:
            round = -0.01
        if self.siteId == 15 and hand.totalcollected > hand.totalpot:
            hand.rake = old_div(hand.totalpot, 10)
            print(hand.rake)
        if hand.rake < 0 and (not hand.roundPenny or hand.rake < round) and not hand.cashedOut:
            if self.siteId == 28 and (
                (hand.rake + Decimal(str(hand.sb)) - (0 if hand.rakes.get("rake") is None else hand.rakes["rake"])) == 0
                or (
                    hand.rake
                    + Decimal(str(hand.sb))
                    + Decimal(str(hand.bb))
                    - (0 if hand.rakes.get("rake") is None else hand.rakes["rake"])
                )
                == 0
            ):
                log.error(
                    ("hhc.getRake(): '%s': Missed sb/bb - Amount collected (%s) is greater than the pot (%s)")
                    % (hand.handid, str(hand.totalcollected), str(hand.totalpot))
                )
            else:
                log.error(
                    ("hhc.getRake(): '%s': Amount collected (%s) is greater than the pot (%s)")
                    % (hand.handid, str(hand.totalcollected), str(hand.totalpot))
                )
                raise FpdbParseError
        elif (
            hand.totalpot > 0
            and Decimal(old_div(hand.totalpot, 4)) < hand.rake
            and not hand.fastFold
            and not hand.cashedOut
        ):
            log.error(
                ("hhc.getRake(): '%s': Suspiciously high rake (%s) > 25 pct of pot (%s)")
                % (hand.handid, str(hand.rake), str(hand.totalpot))
            )
            raise FpdbParseError

    def sanityCheck(self):
        """Check we aren't going to do some stupid things"""
        sane = False
        # base_w = False

        # Make sure input and output files are different or we'll overwrite the source file
        if True:  # basically.. I don't know
            sane = True

        if self.in_path != "-" and self.out_path == self.in_path:
            print(("Output and input files are the same, check config."))
            sane = False

        return sane

    # Functions not necessary to implement in sub class
    def setFileType(self, filetype="text", codepage="utf8"):
        self.filetype = filetype
        self.codepage = codepage

    # Import from string
    def setObs(self, text):
        self.obs = text
        self.whole_file = text

    def __listof(self, x):
        if isinstance(x, list) or isinstance(x, tuple):
            return x
        else:
            return [x]

    def readFile(self):
        """Open in_path according to self.codepage. Exceptions caught further up"""

        if self.filetype == "text":
            for kodec in self.__listof(self.codepage):
                # print "trying", kodec
                try:
                    in_fh = codecs.open(self.in_path, "r", kodec)
                    self.whole_file = in_fh.read()
                    in_fh.close()
                    self.obs = self.whole_file[self.index :]
                    self.index = len(self.whole_file)
                    self.kodec = kodec
                    return True
                except (IOError, UnicodeDecodeError) as e:
                    log.warning(f"Failed to read file with codec {kodec}: {e}")
            else:
                log.error(f"Unable to read file with any codec in list! {self.in_path}")
                self.obs = ""
                return False

        elif self.filetype == "xml":
            if hasattr(self, "in_path"):  # Ensure filename (in_path) is available
                doc = xml.dom.minidom.parse(self.in_path)
                self.doc = doc
            else:
                log.error("No file path provided for XML filetype")
                return False

        elif self.filetype == "":
            pass

    def guessMaxSeats(self, hand):
        """Return a guess at maxseats when not specified in HH."""
        # if some other code prior to this has already set it, return it
        if not self.copyGameHeader and hand.gametype["type"] == "tour":
            return 10

        if self.maxseats > 1 and self.maxseats < 11:
            return self.maxseats

        mo = self.maxOccSeat(hand)

        if mo == 10:
            return 10  # that was easy

        if hand.gametype["base"] == "stud":
            if mo <= 8:
                return 8

        if hand.gametype["base"] == "draw":
            if mo <= 6:
                return 6

        return 10

    def maxOccSeat(self, hand):
        max = 0
        for player in hand.players:
            if int(player[0]) > max:
                max = int(player[0])
        return max

    def getStatus(self):
        # TODO: Return a status of true if file processed ok
        return self.status

    def getProcessedHands(self):
        return self.processedHands

    def getProcessedFile(self):
        return self.out_path

    def getLastCharacterRead(self):
        return self.index

    def isSummary(self, topline):
        return " Tournament Summary " in topline

    def getParsedObjectType(self):
        return self.parsedObjectType

    def getBasename(self):
        head, tail = os.path.split(self.in_path)
        base = tail or os.path.basename(head)
        return base.split(".")[0]

    # returns a status (True/False) indicating wether the parsing could be done correctly or not
    @abstractmethod
    def readSummaryInfo(self, summaryInfoList):
        pass

    def getTourney(self):
        return self.tourney

    @staticmethod
    def changeTimezone(time, givenTimezone, wantedTimezone):
        """Takes a givenTimezone in format AAA or AAA+HHMM where AAA is a standard timezone
        and +HHMM is an optional offset (+/-) in hours (HH) and minutes (MM)
        (See OnGameToFpdb.py for example use of the +HHMM part)
        Tries to convert the time parameter (with no timezone) from the givenTimezone to
        the wantedTimeZone (currently only allows "UTC")
        """
        # log.debug("raw time: " + str(time) + " given time zone: " + str(givenTimezone))
        if wantedTimezone == "UTC":
            wantedTimezone = pytz.utc
        else:
            log.error(("Unsupported target timezone: ") + givenTimezone)
            raise FpdbParseError(("Unsupported target timezone: ") + givenTimezone)

        givenTZ = None
        if HandHistoryConverter.re_tzOffset.match(givenTimezone):
            offset = int(givenTimezone[-5:])
            givenTimezone = givenTimezone[0:-5]
            # log.debug("changeTimeZone: offset=" + str(offset))
        else:
            offset = 0

        if givenTimezone in ("ET", "EST", "EDT"):
            givenTZ = timezone("US/Eastern")
        elif givenTimezone in ("CET", "CEST", "MEZ", "MESZ", "HAEC"):
            # since CEST will only be used in summer time it's ok to treat it as identical to CET.
            givenTZ = timezone("Europe/Berlin")
            # Note: Daylight Saving Time is standardised across the EU so this should be fine
        elif givenTimezone in ("GT", "GMT"):  # GMT is always the same as UTC
            givenTZ = timezone("GMT")
            # GMT cannot be treated as WET because some HH's are explicitly
            # GMT+-delta so would be incorrect during the summertime
            # if substituted as WET+-delta
        elif givenTimezone == "BST":
            givenTZ = timezone("Europe/London")
        elif givenTimezone == "WET":  # WET is GMT with daylight saving delta
            givenTZ = timezone("WET")
        elif givenTimezone in ("HT", "HST", "HDT"):  # Hawaiian Standard Time
            givenTZ = timezone("US/Hawaii")
        elif givenTimezone == "AKT":  # Alaska Time
            givenTZ = timezone("US/Alaska")
        elif givenTimezone in ("PT", "PST", "PDT"):  # Pacific Time
            givenTZ = timezone("US/Pacific")
        elif givenTimezone in ("MT", "MST", "MDT"):  # Mountain Time
            givenTZ = timezone("US/Mountain")
        elif givenTimezone in ("CT", "CST", "CDT"):  # Central Time
            givenTZ = timezone("US/Central")
        elif givenTimezone == "AT":  # Atlantic Time
            givenTZ = timezone("Canada/Atlantic")
        elif givenTimezone == "NT":  # Newfoundland Time
            givenTZ = timezone("Canada/Newfoundland")
        elif givenTimezone == "ART":  # Argentinian Time
            givenTZ = timezone("America/Argentina/Buenos_Aires")
        elif givenTimezone in ("BRT", "BRST"):  # Brasilia Time
            givenTZ = timezone("America/Sao_Paulo")
        elif givenTimezone == "VET":
            givenTZ = timezone("America/Caracas")
        elif givenTimezone == "COT":
            givenTZ = timezone("America/Bogota")
        elif givenTimezone in ("EET", "EEST"):  # Eastern European Time
            givenTZ = timezone("Europe/Bucharest")
        elif givenTimezone in ("MSK", "MESZ", "MSKS", "MSD"):  # Moscow Standard Time
            givenTZ = timezone("Europe/Moscow")
        elif givenTimezone == "GST":
            givenTZ = timezone("Asia/Dubai")
        elif givenTimezone in ("YEKT", "YEKST"):
            givenTZ = timezone("Asia/Yekaterinburg")
        elif givenTimezone in ("KRAT", "KRAST"):
            givenTZ = timezone("Asia/Krasnoyarsk")
        elif givenTimezone == "IST":  # India Standard Time
            givenTZ = timezone("Asia/Kolkata")
        elif givenTimezone == "ICT":
            givenTZ = timezone("Asia/Bangkok")
        elif givenTimezone == "CCT":  # China Coast Time
            givenTZ = timezone("Australia/West")
        elif givenTimezone == "JST":  # Japan Standard Time
            givenTZ = timezone("Asia/Tokyo")
        elif givenTimezone in ("AWST", "AWT"):  # Australian Western Standard Time
            givenTZ = timezone("Australia/West")
        elif givenTimezone in ("ACST", "ACT"):  # Australian Central Standard Time
            givenTZ = timezone("Australia/Darwin")
        elif givenTimezone in ("AEST", "AET"):  # Australian Eastern Standard Time
            # Each State on the East Coast has different DSTs.
            # Melbournce is out because I don't like AFL, Queensland doesn't have DST
            # ACT is full of politicians and Tasmania will never notice.
            # Using Sydney.
            givenTZ = timezone("Australia/Sydney")
        elif givenTimezone in ("NZST", "NZT", "NZDT"):  # New Zealand Time
            givenTZ = timezone("Pacific/Auckland")
        elif givenTimezone == "UTC":  # Universal time co-ordinated
            givenTZ = pytz.UTC
        elif givenTimezone in pytz.all_timezones:
            givenTZ = timezone(givenTimezone)
        else:
            timezone_lookup = dict(
                [(pytz.timezone(x).localize(datetime.datetime.now()).tzname(), x) for x in pytz.all_timezones]
            )
            if givenTimezone in timezone_lookup:
                givenTZ = timezone(timezone_lookup[givenTimezone])

        if givenTZ is None:
            # do not crash if timezone not in list, just return UTC localized time
            log.error(("Timezone conversion not supported") + ": " + givenTimezone + " " + str(time))
            givenTZ = pytz.UTC
            return givenTZ.localize(time)

        localisedTime = givenTZ.localize(time)
        utcTime = localisedTime.astimezone(wantedTimezone) + datetime.timedelta(
            seconds=-3600 * (old_div(offset, 100)) - 60 * (offset % 100)
        )
        # log.debug("utcTime: " + str(utcTime))
        return utcTime

    # end @staticmethod def changeTimezone

    @staticmethod
    def getTableTitleRe(type, table_name=None, tournament=None, table_number=None):
        "Returns string to search in windows titles"
        if type == "tour":
            return re.escape(str(tournament)) + ".+\\Table " + re.escape(str(table_number))
        else:
            return re.escape(table_name)

    @staticmethod
    def getTableNoRe(tournament):
        "Returns string to search window title for tournament table no."
        # Full Tilt:  $30 + $3 Tournament (181398949), Table 1 - 600/1200 Ante 100 - Limit Razz
        # PokerStars: WCOOP 2nd Chance 02: $1,050 NLHE - Tournament 307521826 Table 1 - Blinds $30/$60
        return "%s.+(?:Table|Torneo) (\d+)" % (tournament,)

    @staticmethod
    def clearMoneyString(money):
        """Converts human readable string representations of numbers like
        '1 200', '2,000', '0,01' to more machine processable form - no commas, 1 decimal point
        """
        if not money:
            return money
        money = money.replace(" ", "")
        money = money.replace("\xa0", "")
        if "K" in money:
            money = money.replace("K", "000")
        if "M" in money:
            money = money.replace("M", "000000")
        if "B" in money:
            money = money.replace("B", "000000000")
        if money[-1] in (".", ","):
            money = money[:-1]
        if len(money) < 3:
            return money  # No commas until 0,01 or 1,00
        if money[-3] == ",":
            money = money[:-3] + "." + money[-2:]
            if len(money) > 15:
                if money[-15] == ".":
                    money = money[:-15] + "," + money[-14:]
            if len(money) > 11:
                if money[-11] == ".":
                    money = money[:-11] + "," + money[-10:]
            if len(money) > 7:
                if money[-7] == ".":
                    money = money[:-7] + "," + money[-6:]
        else:
            if len(money) > 12:
                if money[-12] == ".":
                    money = money[:-12] + "," + money[-11:]
            if len(money) > 8:
                if money[-8] == ".":
                    money = money[:-8] + "," + money[-7:]
            if len(money) > 4:
                if money[-4] == ".":
                    money = money[:-4] + "," + money[-3:]

        return money.replace(",", "").replace("'", "")


def getTableTitleRe(config, sitename, *args, **kwargs):
    "Returns string to search in windows titles for current site"
    return getSiteHhc(config, sitename).getTableTitleRe(*args, **kwargs)


def getTableNoRe(config, sitename, *args, **kwargs):
    "Returns string to search window titles for tournament table no."
    return getSiteHhc(config, sitename).getTableNoRe(*args, **kwargs)


def getSiteHhc(config, sitename):
    "Returns HHC class for current site"
    hhcName = config.hhcs[sitename].converter
    hhcModule = __import__(hhcName)
    return getattr(hhcModule, hhcName[:-6])


def get_out_fh(out_path, parameters):
    if out_path == "-":
        return sys.stdout
    elif parameters.get("saveStarsHH", False):
        out_dir = os.path.dirname(out_path)
        if not os.path.isdir(out_dir) and out_dir != "":
            try:
                os.makedirs(out_dir)
            except OSError as e:
                log.error(f"Unable to create output directory {out_dir} for HHC: {e}")
            else:
                log.info(f"Created directory '{out_dir}'")
        try:
            return codecs.open(out_path, "w", "utf8")
        except (IOError, OSError) as e:
            log.error(f"Output path {out_path} couldn't be opened: {e}")
            return None
    else:
        return sys.stdout
