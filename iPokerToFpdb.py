#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#    Copyright 2010-2012, Carl Gherardi
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

########################################################################

# import L10n
# _ = L10n.get_translation()

# This code is based on CarbonToFpdb.py by Matthew Boss
#
# TODO:
#
# -- No support for tournaments (see also the last item below)
# -- Assumes that the currency of ring games is USD
# -- No support for a bring-in or for antes (is the latter in fact unnecessary
#    for hold 'em on Carbon?)
# -- hand.maxseats can only be guessed at
# -- The last hand in a history file will often be incomplete and is therefore
#    rejected
# -- Is behaviour currently correct when someone shows an uncalled hand?
# -- Information may be lost when the hand ID is converted from the native form
#    xxxxxxxx-yyy(y*) to xxxxxxxxyyy(y*) (in principle this should be stored as
#    a string, but the database does not support this). Is there a possibility
#    of collision between hand IDs that ought to be distinct?
# -- Cannot parse tables that run it twice (nor is this likely ever to be
#    possible)
# -- Cannot parse hands in which someone is all in in one of the blinds. Until
#    this is corrected tournaments will be unparseable

from HandHistoryConverter import HandHistoryConverter, FpdbParseError, FpdbHandPartial
from decimal import Decimal
import re
from loggingFpdb import get_logger
import datetime


log = get_logger("parser")


class iPoker(HandHistoryConverter):
    """
    A class for converting iPoker hand history files to the PokerTH format.
    """

    sitename = "iPoker"
    filetype = "text"
    codepage = ("utf8", "cp1252")
    siteId = 14
    copyGameHeader = True  # NOTE: Not sure if this is necessary yet. The file is xml so its likely
    summaryInFile = True

    substitutions = {
        "LS": r"\$|\xe2\x82\xac|\xe2\u201a\xac|\u20ac|\xc2\xa3|\£|RSD|kr|",  # Used to remove currency symbols from the hand history
        "PLYR": r"(?P<PNAME>[^\"]+)",  # Regex pattern for matching player names
        "NUM": r"(.,\d+)|(\d+)",  # Regex pattern for matching numbers
        "NUM2": r"\b((?:\d{1,3}(?:\s\d{3})*)|(?:\d+))\b",  # Regex pattern for matching numbers with spaces
    }

    limits = {
        "No limit": "nl",
        "Pot limit": "pl",
        "Limit": "fl",
        "NL": "nl",
        "SL": "nl",
        "БЛ": "nl",
        "PL": "pl",
        "LP": "pl",
        "L": "fl",
        "LZ": "nl",
    }
    games = {  # base, category
        "7 Card Stud": ("stud", "studhi"),
        "7 Card Stud Hi-Lo": ("stud", "studhilo"),
        "7 Card Stud HiLow": ("stud", "studhilo"),
        "5 Card Stud": ("stud", "5_studhi"),
        "Holdem": ("hold", "holdem"),
        "Six Plus Holdem": ("hold", "6_holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi-Lo": ("hold", "omahahilo"),
        "Omaha HiLow": ("hold", "omahahilo"),
    }

    currencies = {"€": "EUR", "$": "USD", "": "T$", "£": "GBP", "RSD": "RSD", "kr": "SEK"}

    # translations from captured groups to fpdb info strings
    Lim_Blinds = {
        "0.04": ("0.01", "0.02"),
        "0.08": ("0.02", "0.04"),
        "0.10": ("0.02", "0.05"),
        "0.20": ("0.05", "0.10"),
        "0.40": ("0.10", "0.20"),
        "0.50": ("0.10", "0.25"),
        "1.00": ("0.25", "0.50"),
        "1": ("0.25", "0.50"),
        "2.00": ("0.50", "1.00"),
        "2": ("0.50", "1.00"),
        "4.00": ("1.00", "2.00"),
        "4": ("1.00", "2.00"),
        "6.00": ("1.00", "3.00"),
        "6": ("1.00", "3.00"),
        "8.00": ("2.00", "4.00"),
        "8": ("2.00", "4.00"),
        "10.00": ("2.00", "5.00"),
        "10": ("2.00", "5.00"),
        "20.00": ("5.00", "10.00"),
        "20": ("5.00", "10.00"),
        "30.00": ("10.00", "15.00"),
        "30": ("10.00", "15.00"),
        "40.00": ("10.00", "20.00"),
        "40": ("10.00", "20.00"),
        "60.00": ("15.00", "30.00"),
        "60": ("15.00", "30.00"),
        "80.00": ("20.00", "40.00"),
        "80": ("20.00", "40.00"),
        "100.00": ("25.00", "50.00"),
        "100": ("25.00", "50.00"),
        "150.00": ("50.00", "75.00"),
        "150": ("50.00", "75.00"),
        "200.00": ("50.00", "100.00"),
        "200": ("50.00", "100.00"),
        "400.00": ("100.00", "200.00"),
        "400": ("100.00", "200.00"),
        "800.00": ("200.00", "400.00"),
        "800": ("200.00", "400.00"),
        "1000.00": ("250.00", "500.00"),
        "1000": ("250.00", "500.00"),
        "2000.00": ("500.00", "1000.00"),
        "2000": ("500.00", "1000.00"),
    }



    months = {
        "Jan": 1,
        "Feb": 2,
        "Mar": 3,
        "Apr": 4,
        "May": 5,
        "Jun": 6,
        "Jul": 7,
        "Aug": 8,
        "Sep": 9,
        "Oct": 10,
        "Nov": 11,
        "Dec": 12,
    }

    # Static regexes
    re_client = re.compile(r"<client_version>(?P<CLIENT>.*?)</client_version>")
    # re_Identify = re.compile(u"""<\?xml version=\"1\.0\" encoding=\"utf-8\"\?>""")
    re_Identify = re.compile("""<game gamecode=\"\d+\">""")
    re_SplitHands = re.compile(r"</game>")
    re_TailSplitHands = re.compile(r"(</game>)")
    re_GameInfo = re.compile(
        r"""
            <gametype>(?P<GAME>((?P<CATEGORY>(5|7)\sCard\sStud(\sHi\-Lo|\sHiLow)?|(Six\sPlus\s)?Holdem|Omaha(\sHi\-Lo|\sHiLow)?)?\s?(?P<LIMIT>NL|SL|L|LZ|PL|БЛ|LP|No\slimit|Pot\slimit|Limit))|LH\s(?P<LSB>[%(NUM)s]+)(%(LS)s)?/(?P<LBB>[%(NUM)s]+)(%(LS)s)?.+?)
            (\s(%(LS)s)?(?P<SB>[%(NUM)s]+)(%(LS)s)?/(%(LS)s)?(?P<BB>[%(NUM)s]+))?(%(LS)s)?(\sAnte\s(%(LS)s)?(?P<ANTE>[%(NUM)s]+)(%(LS)s)?)?</gametype>\s+?
            <tablename>(?P<TABLE>.+)?</tablename>\s+?
            (<(tablecurrency|tournamentcurrency)>(?P<TABLECURRENCY>.*)</(tablecurrency|tournamentcurrency)>\s+?)?
            (<smallblind>.+</smallblind>\s+?)?
            (<bigblind>.+</bigblind>\s+?)?
            <duration>.+</duration>\s+?
            <gamecount>.+</gamecount>\s+?
            <startdate>.+</startdate>\s+?
            <currency>(?P<CURRENCY>.+)?</currency>\s+?
            <nickname>(?P<HERO>.+)?</nickname>
            """
        % substitutions,
        re.MULTILINE | re.VERBOSE,
    )
    re_GameInfoTrny = re.compile(
        r"""
                        (?:(<tour(?:nament)?code>(?P<TOURNO>\d+)</tour(?:nament)?code>))|
                        (?:(<tournamentname>(?P<NAME>[^<]*)</tournamentname>))|
                        (?:(<rewarddrawn>(?P<REWARD>[%(NUM2)s%(LS)s]+)</rewarddrawn>))| 
                        (?:(<place>(?P<PLACE>.+?)</place>))|
                        (?:(<buyin>(?P<BIAMT>[%(NUM2)s%(LS)s]+)\s\+\s)?(?P<BIRAKE>[%(NUM2)s%(LS)s]+)\s\+\s(?P<BIRAKE2>[%(NUM2)s%(LS)s]+)</buyin>)|
                        (?:(<totalbuyin>(?P<TOTBUYIN>.*)</totalbuyin>))|
                        (?:(<win>(%(LS)s)?(?P<WIN>.+?|[%(NUM2)s%(LS)s]+)</win>))
                        """
        % substitutions,
        re.VERBOSE,
    )
    re_GameInfoTrny2 = re.compile(
        r"""
            (?:(<tour(?:nament)?code>(?P<TOURNO>\d+)</tour(?:nament)?code>))|
            (?:(<tournamentname>(?P<NAME>[^<]*)</tournamentname>))|
            (?:(<place>(?P<PLACE>.+?)</place>))|
            (?:(<buyin>(?P<BIAMT>[%(NUM2)s%(LS)s]+(?:\s\+\s)?(?P<BIRAKE>[%(NUM2)s%(LS)s]+)?)</buyin>))|
            (?:(<totalbuyin>(?P<TOTBUYIN>[%(NUM2)s%(LS)s]+)</totalbuyin>))|
            (?:(<win>(%(LS)s)?(?P<WIN>.+?|[%(NUM2)s%(LS)s]+)</win>))
        """
        % substitutions,
        re.VERBOSE,
    )


    re_Buyin = re.compile(r"""(?:(<totalbuyin>(?P<TOTBUYIN>.*)</totalbuyin>))""", re.VERBOSE)
    re_TotalBuyin = re.compile(
        r"""(?:(<buyin>(?P<BIAMT>[%(NUM2)s%(LS)s]+)\s\+\s)?(?P<BIRAKE>[%(NUM2)s%(LS)s]+)\s\+\s(?P<BIRAKE2>[%(NUM2)s%(LS)s]+)</buyin>)"""
        % substitutions,
        re.VERBOSE,
    )
    re_HandInfo = re.compile(
        r'code="(?P<HID>[0-9]+)">\s*?<general>\s*?<startdate>(?P<DATETIME>[\.a-zA-Z-/: 0-9]+)</startdate>', re.MULTILINE
    )
    re_PlayerInfo = re.compile(
        r'<player( (seat="(?P<SEAT>[0-9]+)"|name="%(PLYR)s"|chips="(%(LS)s)?(?P<CASH>[%(NUM2)s]+)(%(LS)s)?"|dealer="(?P<BUTTONPOS>(0|1))"|win="(%(LS)s)?(?P<WIN>[%(NUM2)s]+)(%(LS)s)?"|bet="(%(LS)s)?(?P<BET>[^"]+)(%(LS)s)?"|addon="\d*"|rebuy="\d*"|merge="\d*"|reg_code="[\d-]*"))+\s*/>'
        % substitutions,
        re.MULTILINE,
    )
    re_Board = re.compile(
        r'<cards( (type="(?P<STREET>Flop|Turn|River)"|player=""))+>(?P<CARDS>.+?)</cards>', re.MULTILINE
    )
    re_EndOfHand = re.compile(r'<round id="END_OF_GAME"', re.MULTILINE)
    re_Hero = re.compile(r"<nickname>(?P<HERO>.+)</nickname>", re.MULTILINE)
    re_HeroCards = re.compile(
        r'<cards( (type="(Pocket|Second\sStreet|Third\sStreet|Fourth\sStreet|Fifth\sStreet|Sixth\sStreet|River)"|player="%(PLYR)s"))+>(?P<CARDS>.+?)</cards>'
        % substitutions,
        re.MULTILINE,
    )
    # re_Action = re.compile(r'<action ((no="(?P<ACT>[0-9]+)"|player="%(PLYR)s"|(actiontxt="[^"]+" turntime="[^"]+")|type="(?P<ATYPE>\d+)"|sum="(%(LS)s)(?P<BET>[%(NUM)s]+)"|cards="[^"]*") ?)*/>' % substitutions, re.MULTILINE)
    re_Action = re.compile(
        r"<action(?:\s+player=\"%(PLYR)s\"|\s+type=\"(?P<ATYPE>\d+)\"|\s+no=\"(?P<ACT>[0-9]+)\"|\s+sum=\"(?P<BET>[%(NUM)s]+)(%(LS)s)\")+/>"
        % substitutions,
        re.MULTILINE,
    )
    re_SitsOut = re.compile(r'<event sequence="[0-9]+" type="SIT_OUT" player="(?P<PSEAT>[0-9])"/>', re.MULTILINE)
    re_DateTime1 = re.compile(
        """(?P<D>[0-9]{2})\-(?P<M>[a-zA-Z]{3})\-(?P<Y>[0-9]{4})\s+(?P<H>[0-9]+):(?P<MIN>[0-9]+)(:(?P<S>[0-9]+))?""",
        re.MULTILINE,
    )
    re_DateTime2 = re.compile(
        """(?P<D>[0-9]{2})[\/\.](?P<M>[0-9]{2})[\/\.](?P<Y>[0-9]{4})\s+(?P<H>[0-9]+):(?P<MIN>[0-9]+)(:(?P<S>[0-9]+))?""",
        re.MULTILINE,
    )
    re_DateTime3 = re.compile(
        """(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})\s+(?P<H>[0-9]+):(?P<MIN>[0-9]+)(:(?P<S>[0-9]+))?""",
        re.MULTILINE,
    )
    re_MaxSeats = re.compile(r"<tablesize>(?P<SEATS>[0-9]+)</tablesize>", re.MULTILINE)
    re_tablenamemtt = re.compile(r"<tablename>(?P<TABLET>.+?)</tablename>", re.MULTILINE)
    re_TourNo = re.compile(r"(?P<TOURNO>\d+)$", re.MULTILINE)
    re_non_decimal = re.compile(r"[^\d.,]+")
    re_Partial = re.compile("<startdate>", re.MULTILINE)
    re_UncalledBets = re.compile("<uncalled_bet_enabled>true<\/uncalled_bet_enabled>")
    re_ClientVersion = re.compile("<client_version>(?P<VERSION>[.\d]+)</client_version>")
    re_FPP = re.compile(r"Pts\s")


    def compilePlayerRegexs(self, hand):
        log.debug(f"Compiling player regexes for hand: {hand}")


    def playerNameFromSeatNo(self, seatNo, hand):
        """
        Returns the name of the player from the given seat number.

        This special function is required because Carbon Poker records actions by seat number, not by the player's name.

        Args:
            seatNo (int): The seat number of the player.
            hand (Hand): The hand instance containing the players information.

        Returns:
            str: The name of the player from the given seat number.
        """
        log.debug(f"Searching for player name from seatNo: {seatNo} in hand: {hand}")
        for p in hand.players:
            log.debug(f"Checking player: {p}")
            if p[0] == int(seatNo):
                log.debug(f"Found player: {p[1]} for seatNo: {seatNo}")
                return p[1]
        log.debug(f"No player found for seatNo: {seatNo}")
        return None

    def readSupportedGames(self):
        """
        Return a list of supported games, where each game is a list of strings.
        The first element of each game list is either "ring" or "tour".
        The second element of each game list is either "stud" or "hold".
        The third element of each game list is either "nl", "pl", or "fl".
        """
        supported_games = [
            ["ring", "stud", "fl"],  # ring game with stud format and fixed limit
            ["ring", "hold", "nl"],  # ring game with hold format and no limit
            ["ring", "hold", "pl"],  # ring game with hold format and pot limit
            ["ring", "hold", "fl"],  # ring game with hold format and fixed limit
            ["tour", "hold", "nl"],  # tournament with hold format and no limit
            ["tour", "hold", "pl"],  # tournament with hold format and pot limit
            ["tour", "hold", "fl"],  # tournament with hold format and fixed limit
            ["tour", "stud", "fl"],  # tournament with stud format and fixed limit
        ]
        log.debug(f"Supported games: {supported_games}")
        return supported_games

    def parseHeader(self, handText, whole_file):
        """
        Parses the header of a hand history and returns the game type.

        Args:
            handText (str): The text containing the header of the hand history.
            whole_file (str): The entire text of the hand history.

        Returns:
            str: The game type, if it can be determined from the header or the whole file.
                None otherwise.

        Raises:
            FpdbParseError: If the hand history is an iPoker hand lacking actions/starttime.
            FpdbHandPartial: If the hand history is an iPoker partial hand history without a start date.
        """
        log.debug(f"Starting parseHeader with handText: {handText[:200]} and whole_file length: {len(whole_file)}")
        
        # Attempt to determine the game type from the hand text
        gametype = self.determineGameType(handText)
        log.debug(f"Game type determined from handText: {gametype}")
        
        if gametype is None:
            # Fallback to determining the game type from the whole file
            gametype = self.determineGameType(whole_file)
            log.debug(f"Game type determined from whole_file: {gametype}")
        
        if gametype is None:
            # Handle iPoker hands lacking actions/starttime and funnel them to partial
            if self.re_Partial.search(whole_file):
                tmp = handText[:200]  # Limit to the first 200 characters for logging
                log.error(f"No game type found. Partial handText: '{tmp}'")
                raise FpdbParseError
            
            else:
                message = "No startdate"
                log.warning(f"iPoker partial hand history detected: {message}")
                raise FpdbHandPartial(f"iPoker partial hand history: {message}")
        
        log.debug(f"Game type successfully parsed: {gametype}")
        return gametype


    def determineGameType(self, handText):
        """
        Given a hand history, extract information about the type of game being played.
        """
        log.debug(f"Starting determineGameType with handText: {handText[:200]}")

        m = self.re_GameInfo.search(handText)
        if not m:
            log.debug("re_GameInfo regex did not match.")
            return None
        else:
            log.debug("re_GameInfo regex matched.")

        m2 = self.re_MaxSeats.search(handText)
        if m2:
            log.debug("re_MaxSeats regex matched.")
        else:
            log.debug("re_MaxSeats regex did not match.")

        m3 = self.re_tablenamemtt.search(handText)
        if m3:
            log.debug("re_tablenamemtt regex matched.")
        else:
            log.debug("re_tablenamemtt regex did not match.")

        self.info = {}
        mg = m.groupdict()
        mg2 = m2.groupdict() if m2 else {}
        mg3 = m3.groupdict() if m3 else {}
        log.debug(f"Initial groupdict from re_GameInfo: {mg}")
        log.debug(f"Groupdict from re_MaxSeats: {mg2}")
        log.debug(f"Groupdict from re_tablenamemtt: {mg3}")

        tourney = False

        if mg.get("GAME", "")[:2] == "LH":
            log.debug("Game starts with 'LH'. Setting CATEGORY to 'Holdem' and LIMIT to 'L'.")
            mg["CATEGORY"] = "Holdem"
            mg["LIMIT"] = "L"
            mg["BB"] = mg.get("LBB", mg.get("BB", ""))
            log.debug(f"Updated mg after 'LH' condition: {mg}")

        if "GAME" in mg:
            if mg.get("CATEGORY") is None:
                log.debug("CATEGORY is None. Setting base to 'hold' and category to '5_omahahi'.")
                self.info["base"], self.info["category"] = ("hold", "5_omahahi")
            else:
                category = mg["CATEGORY"]
                if category in self.games:
                    self.info["base"], self.info["category"] = self.games[category]
                    log.debug(f"Set base and category based on games dict: {self.info['base']}, {self.info['category']}")
                else:
                    log.error(f"Unknown CATEGORY '{category}' encountered.")
                    return None  # ou une autre gestion d'erreur

        if "LIMIT" in mg:
            limit = mg["LIMIT"]
            if limit in self.limits:
                self.info["limitType"] = self.limits[limit]
                log.debug(f"Set limitType to '{self.info['limitType']}' based on LIMIT '{limit}'.")
            else:
                log.error(f"Unknown LIMIT '{limit}' encountered.")
                return None  # ou une autre gestion d'erreur

        if "HERO" in mg and mg["HERO"]:
            self.hero = mg["HERO"]
            log.debug(f"Set hero to '{self.hero}'.")

        if "SB" in mg:
            self.info["sb"] = self.clearMoneyString(mg["SB"])
            log.debug(f"Set small blind (sb) to '{self.info['sb']}'.")
            if not mg["SB"]:
                tourney = True
                log.debug("Small blind is not set. Marking as tournament.")
        
        if "BB" in mg:
            self.info["bb"] = self.clearMoneyString(mg["BB"])
            log.debug(f"Set big blind (bb) to '{self.info['bb']}'.")

        if "SEATS" in mg2:
            self.info["seats"] = mg2["SEATS"]
            log.debug(f"Set number of seats to '{self.info['seats']}'.")

        if self.re_UncalledBets.search(handText):
            self.uncalledbets = False
            log.debug("Uncalled bets are disabled.")
        else:
            self.uncalledbets = True
            log.debug("Uncalled bets are enabled.")
            mv = self.re_ClientVersion.search(handText)
            if mv:
                major_version = mv.group("VERSION").split(".")[0]
                log.debug(f"Client version major number: {major_version}")
                if int(major_version) >= 20:
                    self.uncalledbets = False
                    log.debug("Client version >= 20. Uncalled bets are disabled.")
        
        if tourney:
            log.debug("Processing tournament-specific information.")
            self.info["type"] = "tour"
            self.info["currency"] = "T$"

            if "TABLET" in mg3:
                self.info["table_name"] = mg3["TABLET"]
                log.debug(f"Table name set to '{self.info['table_name']}'.")

            self.tinfo = {}
            mt = self.re_TourNo.search(mg.get("TABLE", ""))
            if mt:
                self.tinfo["tourNo"] = mt.group("TOURNO")
                log.debug(f"Set tourNo to '{self.tinfo['tourNo']}' from re_TourNo.")
            else:
                tourNo = mg.get("TABLE", "").split(",")[-1].strip().split(" ")[0]
                if tourNo.isdigit():
                    self.tinfo["tourNo"] = tourNo
                    log.debug(f"Set tourNo to '{self.tinfo['tourNo']}' from split TABLE.")
                else:
                    log.error("Failed to parse tourNo from TABLE.")
                    raise FpdbParseError("Failed to parse tourNo.")

            self.tablename = "1"
            if not mg.get("CURRENCY") or mg["CURRENCY"] == "fun":
                self.tinfo["buyinCurrency"] = "play"
                log.debug("Buy-in currency set to 'play'.")
            else:
                self.tinfo["buyinCurrency"] = mg["CURRENCY"]
                log.debug(f"Buy-in currency set to '{self.tinfo['buyinCurrency']}'.")

            self.tinfo["buyin"] = 0
            self.tinfo["fee"] = 0
            client_match = self.re_client.search(handText)
            if client_match:
                re_client_split = ".".join(client_match["CLIENT"].split(".")[:2])
                log.debug(f"Client version split: '{re_client_split}'.")
            else:
                re_client_split = ""
                log.debug("No client version match found.")
            
            if re_client_split == "23.5":  # betclic fr
                log.debug("Client split version is '23.5'. Using re_GameInfoTrny regex.")
                matches = list(self.re_GameInfoTrny.finditer(handText))
                log.debug(f"Number of matches found with re_GameInfoTrny: {len(matches)}")
                for idx, match in enumerate(matches):
                    log.debug(f"Match {idx}: {match.groupdict()}")
                if len(matches) > 6:  # Ensure there are at least 7 matches
                    try:
                        mg["TOURNO"] = matches[0].group("TOURNO")
                        mg["NAME"] = matches[1].group("NAME")
                        mg["REWARD"] = matches[2].group("REWARD")
                        mg["PLACE"] = matches[3].group("PLACE")
                        mg["BIAMT"] = matches[4].group("BIAMT")
                        mg["BIRAKE"] = matches[4].group("BIRAKE")
                        mg["BIRAKE2"] = matches[4].group("BIRAKE2")
                        mg["TOTBUYIN"] = matches[5].group("TOTBUYIN")
                        mg["WIN"] = matches[6].group("WIN")
                        log.debug(f"Extracted tournament info: {mg}")
                    except IndexError as e:
                        log.error(f"Insufficient matches for tournament info: {len(matches)} matches found.")
                        log.debug(f"handText: {handText[:500]}")
                        raise FpdbParseError("Insufficient matches for tournament info.") from e
                else:
                    log.error(f"Not enough matches for tournament info: {len(matches)} matches found.")
                    log.debug(f"handText: {handText[:500]}")
                    raise FpdbParseError("Not enough matches for tournament info.")
            else:
                log.debug("Client split version is not '23.5'. Using re_GameInfoTrny2 regex.")
                matches = list(self.re_GameInfoTrny2.finditer(handText))
                log.debug(f"Number of matches found with re_GameInfoTrny2: {len(matches)}")
                for idx, match in enumerate(matches):
                    log.debug(f"Match {idx}: {match.groupdict()}")
                if len(matches) > 5:  # Ensure there are at least 6 matches
                    try:
                        mg["TOURNO"] = matches[0].group("TOURNO")
                        mg["NAME"] = matches[1].group("NAME")
                        mg["PLACE"] = matches[2].group("PLACE")
                        mg["BIAMT"] = matches[3].group("BIAMT")
                        mg["BIRAKE"] = matches[3].group("BIRAKE")
                        mg["TOTBUYIN"] = matches[4].group("TOTBUYIN")
                        mg["WIN"] = matches[5].group("WIN")
                        log.debug(f"Extracted tournament info: {mg}")
                    except IndexError as e:
                        log.error(f"Insufficient matches for tournament info: {len(matches)} matches found.")
                        log.debug(f"handText: {handText[:500]}")
                        raise FpdbParseError("Insufficient matches for tournament info.") from e
                else:
                    log.error(f"Not enough matches for tournament info: {len(matches)} matches found.")
                    log.debug(f"handText: {handText[:500]}")
                    raise FpdbParseError("Not enough matches for tournament info.")

            if mg.get("TOURNO"):
                self.tinfo["tour_name"] = mg.get("NAME", "")
                self.tinfo["tourNo"] = mg["TOURNO"]
                log.debug(f"Set tour_name to '{self.tinfo['tour_name']}' and tourNo to '{self.tinfo['tourNo']}'.")

            if mg.get("PLACE") and mg["PLACE"] != "N/A":
                self.tinfo["rank"] = int(mg["PLACE"])
                log.debug(f"Set rank to '{self.tinfo['rank']}'.")

            if "winnings" not in self.tinfo:
                self.tinfo["winnings"] = 0  # Initialize 'winnings' if it doesn't exist yet
                log.debug("Initialized 'winnings' to 0.")

            if mg.get("WIN") and mg["WIN"] != "N/A":
                try:
                    winnings = int(
                        100 * Decimal(self.clearMoneyString(self.re_non_decimal.sub("", mg["WIN"])))
                    )
                    self.tinfo["winnings"] += winnings
                    log.debug(f"Added winnings: {winnings}. Total winnings: {self.tinfo['winnings']}.")
                except Exception as e:
                    log.error(f"Error parsing winnings: {mg.get('WIN')}")
                    raise FpdbParseError("Error parsing winnings.") from e

            if not mg.get("BIRAKE"):
                m3 = self.re_TotalBuyin.search(handText)
                if m3:
                    mg = m3.groupdict()
                    log.debug(f"Updated mg from re_TotalBuyin: {mg}")
                elif mg.get("BIAMT"):
                    mg["BIRAKE"] = "0"
                    log.debug("Set BIRAKE to '0' because re_TotalBuyin did not match and BIAMT is present.")

            if mg.get("BIAMT") and self.re_FPP.match(mg["BIAMT"]):
                self.tinfo["buyinCurrency"] = "FPP"
                log.debug("Buy-in currency set to 'FPP' based on BIAMT.")

            if mg.get("BIRAKE"):
                mg["BIRAKE"] = self.clearMoneyString(self.re_non_decimal.sub("", mg["BIRAKE"]))
                mg["BIAMT"] = self.clearMoneyString(self.re_non_decimal.sub("", mg["BIAMT"]))
                log.debug(f"Cleaned BIRAKE: {mg['BIRAKE']}, BIAMT: {mg['BIAMT']}")
                
                if re_client_split == "23.5":
                    if mg.get("BIRAKE2"):
                        try:
                            buyin2 = int(
                                100 * Decimal(self.clearMoneyString(self.re_non_decimal.sub("", mg["BIRAKE2"])))
                            )
                            self.tinfo["buyin"] += buyin2
                            log.debug(f"Added BIRAKE2 to buyin: {buyin2}. Total buyin: {self.tinfo['buyin']}.")
                        except Exception as e:
                            log.error(f"Error parsing BIRAKE2: {mg.get('BIRAKE2')}")
                            raise FpdbParseError("Error parsing BIRAKE2.") from e

                    m4 = self.re_Buyin.search(handText)
                    if m4:
                        try:
                            fee = int(
                                100 * Decimal(self.clearMoneyString(self.re_non_decimal.sub("", mg["BIRAKE"])))
                            )
                            self.tinfo["fee"] = fee
                            log.debug(f"Set fee to '{fee}'.")
                            buyin = int(
                                100 * Decimal(self.clearMoneyString(self.re_non_decimal.sub("", mg["BIRAKE2"])))
                            )
                            self.tinfo["buyin"] = buyin
                            log.debug(f"Set buyin to '{buyin}'.")
                        except Exception as e:
                            log.error("Error parsing fee or buyin from BIRAKE/BIRAKE2.")
                            raise FpdbParseError("Error parsing fee or buyin.") from e

            if self.tinfo["buyin"] == 0:
                self.tinfo["buyinCurrency"] = "FREE"
                log.debug("Buy-in currency set to 'FREE' because buyin is 0.")

            if self.tinfo.get("tourNo") is None:
                log.error("Could Not Parse tourNo")
                raise FpdbParseError("Could Not Parse tourNo")

        else:
            log.debug("Processing ring game-specific information.")
            self.info["type"] = "ring"
            self.tablename = mg.get("TABLE", "")
            log.debug(f"Set tablename to '{self.tablename}'.")
            
            if not mg.get("TABLECURRENCY") and not mg.get("CURRENCY"):
                self.info["currency"] = "play"
                log.debug("Currency set to 'play'.")
            elif not mg.get("TABLECURRENCY"):
                self.info["currency"] = mg["CURRENCY"]
                log.debug(f"Currency set to '{self.info['currency']}' based on CURRENCY.")
            else:
                self.info["currency"] = mg["TABLECURRENCY"]
                log.debug(f"Currency set to '{self.info['currency']}' based on TABLECURRENCY.")

            if self.info.get("limitType") == "fl" and mg.get("BB") is not None:
                try:
                    self.info["sb"] = self.Lim_Blinds[self.clearMoneyString(mg["BB"])][0]
                    self.info["bb"] = self.Lim_Blinds[self.clearMoneyString(mg["BB"])][1]
                    log.debug(f"Set sb to '{self.info['sb']}' and bb to '{self.info['bb']}' based on Lim_Blinds.")
                except KeyError as e:
                    tmp = handText[:200]
                    log.error(f"iPokerToFpdb.determineGameType: Lim_Blinds has no lookup for '{mg.get('BB', '')}' - '{tmp}'")
                    raise FpdbParseError("Lim_Blinds lookup failed.") from e

        log.debug(f"Final info: {self.info}")
        return self.info


    def readTourneyResults(self, hand):
        log.info("enter method readTourneyResults.")
        log.debug("Method readTourneyResults non implemented.")
        pass

    def readSummaryInfo(self, summaryInfoList):
        log.info("enter method readSummaryInfo.")
        log.debug("Method readSummaryInfo non implemented.")
        return True

    def readSTP(self, hand):
        log.debug("enter method readSTP.")
        log.debug("Method readSTP non implemented.")
        pass

    def readHandInfo(self, hand):
        """
        Parses the hand text and extracts relevant information about the hand.

        Args:
            hand: An instance of the Hand class that represents the hand being parsed.

        Raises:
            FpdbParseError: If the hand text cannot be parsed.

        Returns:
            None
        """
        log.debug("Entering readHandInfo.")
        # Search for the relevant information in the hand text
        m = self.re_HandInfo.search(hand.handText)
        if m is None:
            tmp = hand.handText[:200]
            log.error(f"iPokerToFpdb.readHandInfo: '{tmp}'")
            raise FpdbParseError

        log.debug("HandInfo regex matched.")
        log.debug(f"Extracted groupdict: {m.groupdict()}")

        # Extract the relevant information from the match object
        m.groupdict()

        # Set the table name and maximum number of seats for the hand
        hand.tablename = self.tablename
        log.debug(f"Set hand.tablename: {hand.tablename}")

        if self.info["seats"]:
            hand.maxseats = int(self.info["seats"])
            log.debug(f"Set hand.maxseats: {hand.maxseats}")

        # Set the hand ID for the hand
        hand.handid = m.group("HID")
        log.debug(f"Set hand.handid: {hand.handid}")

        # Parse the start time for the hand
        if m2 := self.re_DateTime1.search(m.group("DATETIME")):
            log.debug("Matched re_DateTime1.")
            month = self.months[m2.group("M")]
            sec = m2.group("S") or "00"
            datetimestr = f"{m2.group('Y')}/{month}/{m2.group('D')} {m2.group('H')}:{m2.group('MIN')}:{sec}"
            hand.startTime = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S")
            log.debug(f"Parsed hand.startTime: {hand.startTime}")
        else:
            log.debug("Failed to match re_DateTime1, trying alternative formats.")
            try:
                hand.startTime = datetime.datetime.strptime(m.group("DATETIME"), "%Y-%m-%d %H:%M:%S")
                log.debug(f"Parsed hand.startTime using default format: {hand.startTime}")
            except ValueError as e:
                log.warning(f"Failed to parse datetime: {m.group('DATETIME')}. Trying re_DateTime2 or re_DateTime3.")
                if date_match := self.re_DateTime2.search(m.group("DATETIME")):
                    log.debug("Matched re_DateTime2.")
                    datestr = "%d/%m/%Y %H:%M:%S" if "/" in m.group("DATETIME") else "%d.%m.%Y %H:%M:%S"
                    if date_match.group("S") is None:
                        datestr = "%d/%m/%Y %H:%M"
                else:
                    date_match1 = self.re_DateTime3.search(m.group("DATETIME"))
                    if date_match1 is None:
                        log.error(f"iPokerToFpdb.readHandInfo Could not read datetime: '{hand.handid}'")
                        raise FpdbParseError from e
                    datestr = "%Y/%m/%d %H:%M:%S"
                    if date_match1.group("S") is None:
                        datestr = "%Y/%m/%d %H:%M"
                hand.startTime = datetime.datetime.strptime(m.group("DATETIME"), datestr)
                log.debug(f"Parsed hand.startTime using fallback format: {hand.startTime}")

        # If the hand is a tournament hand, set additional information
        if self.info["type"] == "tour":
            log.debug("Hand is a tournament hand, setting tournament-specific info.")
            hand.tourNo = self.tinfo["tourNo"]
            hand.buyinCurrency = self.tinfo["buyinCurrency"]
            hand.buyin = self.tinfo["buyin"]
            hand.fee = self.tinfo["fee"]
            hand.tablename = f"{self.info['table_name']}"
            log.debug(f"Set tournament info: tourNo={hand.tourNo}, buyinCurrency={hand.buyinCurrency}, "
                    f"buyin={hand.buyin}, fee={hand.fee}, tablename={hand.tablename}")

        log.debug("Exiting readHandInfo.")


    def readPlayerStacks(self, hand):
        """
        Extracts player information from the hand text and populates the Hand object with
        player stacks and winnings.

        Args:
            hand (Hand): Hand object to populate with player information.

        Raises:
            FpdbParseError: If there are fewer than 2 players in the hand.

        Returns:
            None
        """
        log.debug(f"Entering readPlayerStacks for hand: {hand.handid}")

        # Initialize dictionaries and regex pattern
        self.playerWinnings, plist = {}, {}
        log.debug("Initialized playerWinnings and plist dictionaries.")

        m = self.re_PlayerInfo.finditer(hand.handText)
        log.debug("Running regex to find player information in hand text.")

        # Extract player information from regex matches
        for a in m:
            log.debug(f"Matched player info: {a.groupdict()}")
            # Create a dictionary entry for the player with their seat, stack, winnings,
            # and sitout status
            plist[a.group("PNAME")] = [
                int(a.group("SEAT")),
                self.clearMoneyString(a.group("CASH")),
                self.clearMoneyString(a.group("WIN")),
                False,
            ]
            log.debug(f"Player {a.group('PNAME')} added to plist with seat {a.group('SEAT')}, "
                    f"stack {plist[a.group('PNAME')][1]}, winnings {plist[a.group('PNAME')][2]}.")

            # If the player is the button, set the button position in the Hand object
            if a.group("BUTTONPOS") == "1":
                hand.buttonpos = int(a.group("SEAT"))
                log.debug(f"Set button position to seat {hand.buttonpos} for player {a.group('PNAME')}.")

        # Ensure there are at least 2 players in the hand
        if len(plist) <= 1:
            log.error(f"iPokerToFpdb.readPlayerStacks: Less than 2 players in hand '{hand.handid}'.")
            raise FpdbParseError

        log.debug(f"Player list extracted successfully. Total players: {len(plist)}")

        # Add remaining players to the Hand object and playerWinnings dictionary if they won
        for pname in plist:
            seat, stack, win, sitout = plist[pname]
            log.debug(f"Adding player {pname} to hand with seat {seat}, stack {stack}, winnings {win}.")
            hand.addPlayer(seat, pname, stack, None, sitout)
            if Decimal(win) != 0:
                self.playerWinnings[pname] = win
                log.debug(f"Player {pname} has winnings: {win}")

        # Set the maxseats attribute in the Hand object if it is not already set
        if hand.maxseats is None:
            log.debug("Determining hand.maxseats.")
            if self.info["type"] == "tour" and self.maxseats == 0:
                hand.maxseats = self.guessMaxSeats(hand)
                self.maxseats = hand.maxseats
                log.debug(f"Guessed maxseats for tournament: {hand.maxseats}")
            elif self.info["type"] == "tour":
                hand.maxseats = self.maxseats
                log.debug(f"Set maxseats from tournament info: {hand.maxseats}")
            else:
                hand.maxseats = None
                log.debug("maxseats could not be determined and remains None.")

        log.debug("Exiting readPlayerStacks.")


    def markStreets(self, hand):
        """
        Extracts the rounds of a hand and adds them to the Hand object

        Args:
            hand (Hand): the Hand object to which the rounds will be added
        """
        log.debug(f"Entering markStreets for hand: {hand.handid}")

        if hand.gametype["base"] in ("hold"):
            log.debug("Parsing streets for Hold'em game.")
            m = re.search(
                r'(?P<PREFLOP>.+(?=<round no="2">)|.+)'  # Preflop round
                r'(<round no="2">(?P<FLOP>.+(?=<round no="3">)|.+))?'  # Flop round
                r'(<round no="3">(?P<TURN>.+(?=<round no="4">)|.+))?'  # Turn round
                r'(<round no="4">(?P<RIVER>.+))?',  # River round
                hand.handText,
                re.DOTALL,
            )
        elif hand.gametype["base"] in ("stud"):
            log.debug("Parsing streets for Stud game.")
            if hand.gametype["category"] == "5_studhi":
                log.debug("Parsing streets for 5-card Stud High game.")
                m = re.search(
                    r'(?P<ANTES>.+(?=<round no="2">)|.+)'  # Antes round
                    r'(<round no="2">(?P<SECOND>.+(?=<round no="3">)|.+))?'  # Second round
                    r'(<round no="3">(?P<THIRD>.+(?=<round no="4">)|.+))?'  # Third round
                    r'(<round no="4">(?P<FOURTH>.+(?=<round no="5">)|.+))?'  # Fourth round
                    r'(<round no="5">(?P<FIFTH>.+))?',  # Fifth round
                    hand.handText,
                    re.DOTALL,
                )
            else:
                log.debug("Parsing streets for 7-card Stud High/Low game.")
                m = re.search(
                    r'(?P<ANTES>.+(?=<round no="2">)|.+)'  # Antes round
                    r'(<round no="2">(?P<THIRD>.+(?=<round no="3">)|.+))?'  # Third round
                    r'(<round no="3">(?P<FOURTH>.+(?=<round no="4">)|.+))?'  # Fourth round
                    r'(<round no="4">(?P<FIFTH>.+(?=<round no="5">)|.+))?'  # Fifth round
                    r'(<round no="5">(?P<SIXTH>.+(?=<round no="6">)|.+))?'  # Sixth round
                    r'(<round no="6">(?P<SEVENTH>.+))?',  # Seventh round
                    hand.handText,
                    re.DOTALL,
                )

        if m:
            log.debug(f"Streets regex matched. Groups: {m.groupdict()}")
            hand.addStreets(m)
            log.debug("Streets added to hand object.")
        else:
            log.warning(f"No streets matched for hand: {hand.handid}")

        log.debug("Exiting markStreets.")


    def readCommunityCards(self, hand, street):
        """
        Parse the community cards for the given street and set them in the hand object.

        Args:
            hand (Hand): The hand object.
            street (str): The street to parse the community cards for.

        Raises:
            FpdbParseError: If the community cards could not be parsed.

        Returns:
            None
        """
        log.debug(f"Entering readCommunityCards for hand: {hand.handid}, street: {street}")
        cards = []

        try:
            # Search for the board cards in the hand's streets
            if m := self.re_Board.search(hand.streets[street]):
                log.debug(f"Regex matched for community cards on street: {street}. Match groups: {m.groupdict()}")
                # Split the card string into a list of cards
                cards = m.group("CARDS").strip().split(" ")
                log.debug(f"Extracted raw cards: {cards}")

                # Format the cards
                cards = [c[1:].replace("10", "T") + c[0].lower() for c in cards]
                log.debug(f"Formatted cards: {cards}")

                # Set the community cards in the hand object
                hand.setCommunityCards(street, cards)
                log.debug(f"Community cards set for street {street}: {cards}")
            else:
                # Log an error if the board cards could not be found
                log.error(f"iPokerToFpdb.readCommunityCards: No community cards found for hand {hand.handid}, street: {street}")
                raise FpdbParseError
        except Exception as e:
            log.exception(f"Exception occurred while reading community cards for hand {hand.handid}, street: {street}: {e}")
            raise

        log.debug(f"Exiting readCommunityCards for hand: {hand.handid}, street: {street}")


    def readAntes(self, hand):
        """
        Reads the antes for each player in the given hand.

        Args:
            hand (Hand): The hand to read the antes from.

        Returns:
            None
        """
        log.debug(f"Entering readAntes for hand: {hand.handid}")

        # Find all the antes in the hand text using a regular expression
        m = self.re_Action.finditer(hand.handText)
        log.debug("Searching for antes in hand text.")

        # Loop through each ante found
        for a in m:
            log.debug(f"Matched action: {a.groupdict()}")
            # If the ante is of type 15, add it to the hand
            if a.group("ATYPE") == "15":
                player_name = a.group("PNAME")
                ante_amount = self.clearMoneyString(a.group("BET"))
                log.debug(f"Adding ante for player: {player_name}, amount: {ante_amount}")
                hand.addAnte(player_name, ante_amount)

        log.debug(f"Exiting readAntes for hand: {hand.handid}")


    def readBringIn(self, hand):
        """
        Reads the bring-in for a hand and sets the small blind (sb) and big blind (bb) values if they are not already set.

        Args:
            hand (Hand): The hand object for which to read the bring-in.

        Returns:
            None
        """
        log.debug(f"Entering readBringIn for hand: {hand.handid}")
        if hand.gametype["sb"] is None and hand.gametype["bb"] is None:
            hand.gametype["sb"] = "1"  # default small blind value
            hand.gametype["bb"] = "2"  # default big blind value
            log.debug("Small blind and big blind not set. Default values assigned: sb=1, bb=2.")
        log.debug(f"Exiting readBringIn for hand: {hand.handid}")

    def readBlinds(self, hand):
        """
        Parses hand history to extract blind information for each player in the hand.

        :param hand: Hand object containing the hand history.
        :type hand: Hand
        """
        log.debug(f"Entering readBlinds for hand: {hand.handid}")

        # Find all actions in the preflop street
        log.debug("Searching for small blind actions in PREFLOP street.")
        for a in self.re_Action.finditer(hand.streets["PREFLOP"]):
            if a.group("ATYPE") == "1":
                player_name = a.group("PNAME")
                sb_amount = self.clearMoneyString(a.group("BET"))
                log.debug(f"Small blind detected: Player={player_name}, Amount={sb_amount}")
                hand.addBlind(player_name, "small blind", sb_amount)
                if not hand.gametype["sb"]:
                    hand.gametype["sb"] = sb_amount
                    log.debug(f"Small blind amount set in gametype: {sb_amount}")

        # Find all actions in the preflop street for big blinds
        log.debug("Searching for big blind actions in PREFLOP street.")
        m = self.re_Action.finditer(hand.streets["PREFLOP"])
        blinds = {int(a.group("ACT")): a.groupdict() for a in m if a.group("ATYPE") == "2"}
        log.debug(f"Big blinds found: {len(blinds)} players.")

        for b in sorted(list(blinds.keys())):
            blind = blinds[b]
            player_name = blind["PNAME"]
            bet_amount = self.clearMoneyString(blind["BET"])
            blind_type = "big blind"
            log.debug(f"Processing big blind: Player={player_name}, Amount={bet_amount}")

            if not hand.gametype["bb"]:
                hand.gametype["bb"] = bet_amount
                log.debug(f"Big blind amount set in gametype: {bet_amount}")
            elif hand.gametype["sb"]:
                bb = Decimal(hand.gametype["bb"])
                amount = Decimal(bet_amount)
                if amount > bb:
                    blind_type = "both"
                    log.debug(f"Player {player_name} posted both blinds: Amount={bet_amount}")
            hand.addBlind(player_name, blind_type, bet_amount)

        # Fix tournament blinds if necessary
        log.debug("Fixing tournament blinds if necessary.")
        self.fixTourBlinds(hand)

        log.debug(f"Exiting readBlinds for hand: {hand.handid}")


    def fixTourBlinds(self, hand):
        """
        Fix tournament blinds if small blind is missing or sb/bb is all-in.

        :param hand: A dictionary containing the game type information.
        :return: None
        """
        log.debug(f"Entering fixTourBlinds for hand: {hand.handid}")
        if hand.gametype["type"] != "tour":
            log.debug("Hand type is not 'tour'. Exiting fixTourBlinds.")
            return

        log.debug(f"Initial gametype blinds: sb={hand.gametype['sb']}, bb={hand.gametype['bb']}")
        if hand.gametype["sb"] is None and hand.gametype["bb"] is None:
            hand.gametype["sb"] = "1"
            hand.gametype["bb"] = "2"
            log.debug("Blinds missing. Default values assigned: sb=1, bb=2.")
        elif hand.gametype["sb"] is None:
            hand.gametype["sb"] = str(int(int(hand.gametype["bb"]) // 2))
            log.debug(f"Small blind missing. Calculated and set to: sb={hand.gametype['sb']}")
        elif hand.gametype["bb"] is None:
            hand.gametype["bb"] = str(int(hand.gametype["sb"]) * 2)
            log.debug(f"Big blind missing. Calculated and set to: bb={hand.gametype['bb']}")

        if int(hand.gametype["bb"]) // 2 != int(hand.gametype["sb"]):
            if int(hand.gametype["bb"]) // 2 < int(hand.gametype["sb"]):
                hand.gametype["bb"] = str(int(hand.gametype["sb"]) * 2)
                log.debug(f"Big blind adjusted to match small blind: bb={hand.gametype['bb']}")
            else:
                hand.gametype["sb"] = str(int(hand.gametype["bb"]) // 2)
                log.debug(f"Small blind adjusted to match big blind: sb={hand.gametype['sb']}")
        log.debug(f"Final gametype blinds: sb={hand.gametype['sb']}, bb={hand.gametype['bb']}")
        log.debug(f"Exiting fixTourBlinds for hand: {hand.handid}")

    def readButton(self, hand):
        """
        Placeholder for future implementation of button reading.
        """
        log.debug(f"Entering readButton for hand: {hand.handid}. Currently no implementation.")
        pass

    def readHoleCards(self, hand):
        """
        Parses a Hand object to extract hole card information for each player on each street.
        Adds the hole card information to the Hand object.

        Args:
            hand: Hand object to extract hole card information from

        Returns:
            None
        """
        log.debug(f"Entering readHoleCards for hand: {hand.handid}")

        # Streets PREFLOP, PREDRAW, and THIRD require hero's cards
        for street in ("PREFLOP", "DEAL"):
            if street in hand.streets:
                log.debug(f"Processing street: {street} for hero's cards.")
                for found in self.re_HeroCards.finditer(hand.streets[street]):
                    player = found.group("PNAME")
                    cards = found.group("CARDS").split(" ")
                    cards = [c[1:].replace("10", "T") + c[0].lower().replace("x", "") for c in cards]
                    if player == self.hero and cards[0]:
                        hand.hero = player
                        log.debug(f"Hero identified: {player} with cards: {cards}")
                    hand.addHoleCards(street, player, closed=cards, shown=True, mucked=False, dealt=True)

        # Process remaining streets
        for street, text in hand.streets.items():
            if not text or street in ("PREFLOP", "DEAL"):
                continue  # already done these
            log.debug(f"Processing street: {street} for all players.")
            for found in self.re_HeroCards.finditer(text):
                player = found.group("PNAME")
                if player is not None:
                    cards = found.group("CARDS").split(" ")
                    if street == "SEVENTH" and self.hero != player:
                        newcards = []
                        oldcards = [c[1:].replace("10", "T") + c[0].lower() for c in cards if c[0].lower() != "x"]
                    else:
                        newcards = [c[1:].replace("10", "T") + c[0].lower() for c in cards if c[0].lower() != "x"]
                        oldcards = []

                    if street == "THIRD" and len(newcards) == 3 and self.hero == player:
                        hand.hero = player
                        hand.dealt.add(player)
                        hand.addHoleCards(
                            street,
                            player,
                            closed=newcards[:2],
                            open=[newcards[2]],
                            shown=True,
                            mucked=False,
                            dealt=False,
                        )
                        log.debug(f"Hero cards on THIRD street: {newcards[:2]} (closed), {newcards[2]} (open)")
                    elif street == "SECOND" and len(newcards) == 2 and self.hero == player:
                        hand.hero = player
                        hand.dealt.add(player)
                        hand.addHoleCards(
                            street,
                            player,
                            closed=[newcards[0]],
                            open=[newcards[1]],
                            shown=True,
                            mucked=False,
                            dealt=False,
                        )
                        log.debug(f"Hero cards on SECOND street: {newcards[0]} (closed), {newcards[1]} (open)")
                    else:
                        hand.addHoleCards(
                            street, player, open=newcards, closed=oldcards, shown=True, mucked=False, dealt=False
                        )
                        log.debug(f"Player {player} cards on {street}: {newcards} (open), {oldcards} (closed)")

        log.debug(f"Exiting readHoleCards for hand: {hand.handid}")


    def readAction(self, hand, street):
        """
        Extracts actions from a hand and adds them to the corresponding street in a Hand object.

        Args:
            hand (Hand): Hand object to which the actions will be added.
            street (int): Number of the street in the hand (0 for preflop, 1 for flop, etc.).

        Returns:
            None
        """
        log.debug(f"Entering readAction for hand: {hand.handid}, street: {street}")

        # HH format doesn't actually print the actions in order!
        log.debug(f"Parsing actions for street: {street}")
        m = self.re_Action.finditer(hand.streets[street])
        actions = {int(a.group("ACT")): a.groupdict() for a in m}
        log.debug(f"Actions found: {len(actions)}")

        # Add each action to the corresponding method of the Hand object.
        for a in sorted(actions.keys()):
            action = actions[a]
            atype = action["ATYPE"]
            player = action["PNAME"]
            bet = self.clearMoneyString(action["BET"])

            log.debug(f"Processing action: Player={player}, Type={atype}, Bet={bet}")
            if atype == "0":
                hand.addFold(street, player)
                log.debug(f"Added fold for player {player} on street {street}.")
            elif atype == "4":
                hand.addCheck(street, player)
                log.debug(f"Added check for player {player} on street {street}.")
            elif atype == "3":
                hand.addCall(street, player, bet)
                log.debug(f"Added call for player {player} on street {street}, Bet={bet}.")
            elif atype == "23":
                hand.addRaiseTo(street, player, bet)
                log.debug(f"Added raise to {bet} for player {player} on street {street}.")
            elif atype == "6":
                hand.addRaiseBy(street, player, bet)
                log.debug(f"Added raise by {bet} for player {player} on street {street}.")
            elif atype == "5":
                hand.addBet(street, player, bet)
                log.debug(f"Added bet of {bet} for player {player} on street {street}.")
            elif atype == "16":
                hand.addBringIn(player, bet)
                log.debug(f"Added bring-in of {bet} for player {player}.")
            elif atype == "7":
                hand.addAllIn(street, player, bet)
                log.debug(f"Added all-in of {bet} for player {player} on street {street}.")
            elif atype == "15":
                log.debug(f"Ante action skipped for player {player} (handled in readAntes).")
            elif atype in ["1", "2", "8"]:
                log.debug(f"Blind or no-action skipped for player {player} (Type={atype}).")
            elif atype == "9":
                hand.addFold(street, player)
                log.debug(f"Player {player} sitting out, added fold for street {street}.")
            else:
                log.error(f"Unimplemented readAction: Player={player}, Type={atype}")

        log.debug(f"Exiting readAction for hand: {hand.handid}, street: {street}")


    def readShowdownActions(self, hand):
        """
        Reads showdown actions and updates the hand object.

        Args:
            hand (Hand): The hand object to update with showdown actions.

        Returns:
            None
        """
        log.debug(f"Entering readShowdownActions for hand: {hand.handid}")
        # Placeholder for showdown action logic
        log.debug("Currently no implementation for readShowdownActions.")
        log.debug(f"Exiting readShowdownActions for hand: {hand.handid}")

    def readCollectPot(self, hand):
        """
        Sets the uncalled bets for the given hand and adds collect pot actions for each player with non-zero winnings.

        Args:
            hand: The Hand object to update with the collect pot actions.

        Returns:
            None
        """
        log.debug(f"Entering readCollectPot for hand: {hand.handid}")
        hand.setUncalledBets(self.uncalledbets)
        log.debug(f"Uncalled bets set for hand: {self.uncalledbets}")

        for pname, pot in self.playerWinnings.items():
            pot_value = self.clearMoneyString(pot)
            hand.addCollectPot(player=pname, pot=pot_value)
            log.debug(f"Added collect pot action: Player={pname}, Pot={pot_value}")

        log.debug(f"Exiting readCollectPot for hand: {hand.handid}")

    def readShownCards(self, hand):
        """
        Reads shown cards and updates the hand object.

        Args:
            hand (Hand): The hand object to update with shown cards.

        Returns:
            None
        """
        log.debug(f"Entering readShownCards for hand: {hand.handid}")
        # Placeholder for shown cards logic
        log.debug("Currently no implementation for readShownCards.")
        log.debug(f"Exiting readShownCards for hand: {hand.handid}")


    @staticmethod
    def getTableTitleRe(type, table_name=None, tournament=None, table_number=None):
        """
        Generate a regular expression pattern for table title.

        Args:
        - type: A string value.
        - table_name: A string value representing the table name.
        - tournament: A string value representing the tournament.
        - table_number: An integer value representing the table number.

        Returns:
        - A string value representing the regular expression pattern for table title.
        """
        # Log the input parameters
        log.info(f"iPoker table_name='{table_name}' tournament='{tournament}' table_number='{table_number}'")

        # Generate the regex pattern based on the input parameters
        regex = f"{table_name}"

        if type == "tour":
            regex = f"([^\(]+)\s{table_number}"
            log.debug(f"Generated regex for 'tour': {regex}")
            return regex
        elif table_name.find("(No DP),") != -1:
            regex = table_name.split("(No DP),")[0]
        elif table_name.find(",") != -1:
            regex = table_name.split(",")[0]
        else:
            regex = table_name.split(" ")[0]

        # Log the generated regex pattern and return it
        log.info(f"iPoker returns: '{regex}'")
        return regex
