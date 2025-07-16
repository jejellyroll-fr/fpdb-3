#!/usr/bin/env python
#
#    Copyright 2016, Chaz Littlejohn
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

# TODO: straighten out discards for draw games

import datetime
import re
from decimal import Decimal

# _ = L10n.get_translation()
from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger

# Winning HH Format
log = get_logger("parser")


class Winning(HandHistoryConverter):
    # Class Variables

    version = 0
    sitename = "WinningPoker"
    filetype = "text"
    codepage = ("utf8", "cp1252", "utf-16")
    siteId = 24  # Needs to match id entry in Sites database
    sym = {"USD": r"\$", "T$": "", "play": ""}
    substitutions = {
        "LEGAL_ISO": "USD|TB|CP",
        "LS": r"\$",
        "PLYR": r"(?P<PNAME>.+?)",
        "NUM": r".,\dK",
        "CUR": r"(\$|)",
        "BRKTS": r"(\(button\)\s|\(small\sblind\)\s|\(big\sblind\)\s|\(button\)\s\(small\sblind\)\s|\(button\)\s\(big\sblind\)\s)?",
    }

    games1 = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "Six Plus Hold'em": ("hold", "6_holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha HiLow": ("hold", "omahahilo"),
        "5Card Omaha H/L": ("hold", "5_omaha8"),
        "5Card Omaha": ("hold", "5_omahahi"),
        "4Card Omaha H/L": ("hold", "4_omaha8"),
        "4Card Omaha": ("hold", "4_omahahi"),
        "5Card Omaha H/L Reshuffle": ("hold", "5_omaha8"),
        "5Card Omaha Reshuffle": ("hold", "5_omahahi"),
        "4Card Omaha H/L Reshuffle": ("hold", "4_omaha8"),
        "4Card Omaha Reshuffle": ("hold", "4_omahahi"),
        "Seven Cards Stud": ("stud", "studhi"),
        "Seven Cards Stud HiLow": ("stud", "studhilo"),
    }

    games2 = {  # base, category
        "Holdem": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha H/L": ("hold", "omahahilo"),
        "5Card Omaha H/L": ("hold", "5_omaha8"),
        "5Card Omaha": ("hold", "5_omahahi"),
        "4Card Omaha H/L": ("hold", "4_omaha8"),
        "4Card Omaha": ("hold", "4_omahahi"),
        "5Card Omaha H/L Reshuffle": ("hold", "5_omaha8"),
        "5Card Omaha Reshuffle": ("hold", "5_omahahi"),
        "4Card Omaha H/L Reshuffle": ("hold", "4_omaha8"),
        "4Card Omaha Reshuffle": ("hold", "4_omahahi"),
        "7Stud": ("stud", "studhi"),
        "7Stud H/L": ("stud", "studhilo"),
    }

    limits = {
        "No Limit": "nl",
        "Pot Limit": "pl",
        "Fixed Limit": "fl",
        "All-in or Fold Limit": "al",
    }
    speeds = {"Turbo": "Turbo", "Hyper Turbo": "Hyper", "Regular": "Normal"}
    buyin = {"CAP": "cap", "Short": "shallow"}

    SnG_Fee = {
        50: {"Hyper": 0, "Turbo": 0, "Normal": 5},
        100: {"Hyper": 0, "Turbo": 0, "Normal": 10},
        150: {"Hyper": 11, "Turbo": 12, "Normal": 15},
        300: {"Hyper": 20, "Turbo": 25, "Normal": 30},
        500: {"Hyper": 30, "Turbo": 45, "Normal": 50},
        1000: {"Hyper": 55, "Turbo": 90, "Normal": 100},
        1500: {"Hyper": 80, "Turbo": 140, "Normal": 150},
        2000: {"Hyper": 100, "Turbo": 175, "Normal": 200},
        3000: {"Hyper": 130, "Turbo": 275, "Normal": 300},
        5000: {"Hyper": 205, "Turbo": 475, "Normal": 500},
        8000: {"Hyper": 290, "Turbo": 650, "Normal": 800},
        10000: {"Hyper": 370, "Turbo": 800, "Normal": 900},
    }

    HUSnG_Fee = {
        200: {"Hyper": 10, "Turbo": 0, "Normal": 17},
        220: {"Hyper": 0, "Turbo": 16, "Normal": 0},
        240: {"Hyper": 10, "Turbo": 0, "Normal": 0},
        500: {"Hyper": 0, "Turbo": 0, "Normal": 25},
        550: {"Hyper": 0, "Turbo": 25, "Normal": 0},
        600: {"Hyper": 18, "Turbo": 0, "Normal": 0},
        1000: {"Hyper": 25, "Turbo": 0, "Normal": 50},
        1100: {"Hyper": 0, "Turbo": 50, "Normal": 0},
        1200: {"Hyper": 25, "Turbo": 0, "Normal": 0},
        2000: {"Hyper": 50, "Turbo": 0, "Normal": 100},
        2200: {"Hyper": 0, "Turbo": 100, "Normal": 0},
        2400: {"Hyper": 50, "Turbo": 0, "Normal": 0},
        3000: {"Hyper": 70, "Turbo": 0, "Normal": 150},
        3300: {"Hyper": 0, "Turbo": 150, "Normal": 0},
        3600: {"Hyper": 75, "Turbo": 0, "Normal": 0},
        5000: {"Hyper": 100, "Turbo": 0, "Normal": 250},
        5500: {"Hyper": 0, "Turbo": 250, "Normal": 0},
        6000: {"Hyper": 125, "Turbo": 0, "Normal": 0},
        10000: {"Hyper": 200, "Turbo": 0, "Normal": 450},
        11000: {"Hyper": 0, "Turbo": 450, "Normal": 0},
        12000: {"Hyper": 225, "Turbo": 0, "Normal": 0},
        15000: {"Hyper": 266, "Turbo": 0, "Normal": 0},
        20000: {"Hyper": 400, "Turbo": 0, "Normal": 900},
        22000: {"Hyper": 0, "Turbo": 900, "Normal": 0},
        24000: {"Hyper": 450, "Turbo": 0, "Normal": 0},
        30000: {"Hyper": 600, "Turbo": 0, "Normal": 1200},
        33000: {"Hyper": 0, "Turbo": 1200, "Normal": 0},
        36000: {"Hyper": 600, "Turbo": 0, "Normal": 0},
        40000: {"Hyper": 800, "Turbo": 0, "Normal": 0},
        50000: {"Hyper": 0, "Turbo": 0, "Normal": 5000},
        55000: {"Hyper": 0, "Turbo": 2000, "Normal": 0},
        60000: {"Hyper": 1000, "Turbo": 0, "Normal": 0},
        110000: {"Hyper": 0, "Turbo": 3000, "Normal": 0},
        120000: {"Hyper": 1500, "Turbo": 0, "Normal": 0},
    }
    currencies = {"$": "USD", "": "T$"}

    re_GameInfo1 = re.compile(
        """
        Game\\sID:\\s(?P<HID>\\d+)\\s
        (?P<SB>[{NUM}]+)/(?P<BB>[{NUM}]+)\\s
        (?P<TABLE>.+?)?\\s
        \\((?P<GAME>(Six\\sPlus\\s)?Hold\'em|Omaha|Omaha\\sHiLow|Seven\\sCards\\sStud|Seven\\sCards\\sStud\\sHiLow)\\)
        (\\s(?P<MAX>\\d+\\-max))?$
        """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    # Hand #78708209 - Omaha H/L(Fixed Limit) - $20.00/$40.00 - 2019/07/18 15:13:01 UTC
    # Hand #68217077 - Holdem(No Limit) - $0.05/$0.10 - 2019/06/28 02:38:17 UTC
    # Game Hand #80586589 - Tournament #11182752 - Holdem(No Limit) - Level 15 (250.00/500.00)- 2019/07/21 17:44:50 UTC
    # Game Hand #82980175 - Tournament #11212445 - Omaha H/L(Pot Limit) - Level 1 (250.00/500.00)- 2019/07/25 02:31:33 UTC

    re_GameInfo2 = re.compile(
        r"""
        (Game\s)?Hand\s\#(?P<HID>\d+)\s-\s
        (?:(?P<TOUR>(?P<GTD>[\$.,\dK]+\sGTD\s)?Tournament\s\#(?P<TOURNO>\d+)\s-\s))?
        (?P<GAME>Holdem|Omaha|Omaha\sH/L|4Card\sOmaha\sH/L|4Card\sOmaha|5Card\sOmaha\sH/L|5Card\sOmaha|
        4Card\sOmaha\sH/L\sReshuffle|4Card\sOmaha\sReshuffle|5Card\sOmaha\sH/L\sReshuffle|5Card\sOmaha\sReshuffle|7Stud|7Stud\sH/L)\s
        \((?P<LIMIT>No\sLimit|Fixed\sLimit|Pot\sLimit|All\-in\sor\sFold\sLimit)\)\s-\s
        (Level\s(?P<LEVEL>[IVXLC\d]+)\s)?
        \$?(?P<SB>[.0-9]+)/\$?(?P<BB>[.0-9]+)\s-\s
        (?P<DATETIME>\d{4}/\d{2}/\d{2}\s\d{2}:\d{2}:\d{2}\sUTC)
        """,
        re.MULTILINE | re.VERBOSE,
    )

    # Seat 6: puccini (5.34).
    re_PlayerInfo1 = re.compile(
        r"""
        ^Seat\s(?P<SEAT>[0-9]+):\s
        (?P<PNAME>.*)\s
        \((?P<CASH>[{NUM}]+)\)
        \.$
        """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_PlayerInfo2 = re.compile(
        r"""
        ^\s?Seat\s(?P<SEAT>[0-9]+):\s
        (?P<PNAME>.*)\s
        \(({LS})?(?P<CASH>[,.0-9]+)
        \)
        (?P<SITOUT>\sis\ssitting\sout)?""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_DateTime1 = re.compile(
        r"""
        ^Game\sstarted\sat:\s
        (?P<Y>[0-9]{4})/(?P<M>[0-9]{1,2})/(?P<D>[0-9]{1,2})\s
        (?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)
        $""",
        re.MULTILINE | re.VERBOSE,
    )

    # 2019/07/18 15:13:01 UTC
    re_DateTime2 = re.compile(
        r"""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""",
        re.MULTILINE,
    )

    # $2.20 Turbo Heads-up, Table 1
    # $2.40 Hyper Turbo Heads-up, Table 1
    # $10 Freeroll - On Demand, Table 13
    # $25 GTD - On Demand, Table 1
    # $5 Regular 9-Max, Table 1 (Hold'em)

    re_Table1 = re.compile(
        r"""
        ^(?P<CURRENCY>[{LS}]|)?(?P<BUYIN>[{NUM}]+)\s
        ((?P<GAME>(Six\sPlus\s)?Holdem|PLO|PLO8|Omaha\sHi/Lo|Omaha|PL\sOmaha|PL\sOmaha\sHi/Lo|PLO\sHi/Lo)\s?)?
        ((?P<SPECIAL>(GTD|Freeroll|FREEBUY|Freebuy))\s?)?
        ((?P<SPEED>(Turbo|Hyper\sTurbo|Regular))\s?)?
        ((?P<MAX>(\d+\-Max|Heads\-up|Heads\-Up))\s?)?
        (?P<OTHER>.*?)
        ,\sTable\s(?P<TABLENO>\d+)
        """.format(**substitutions),
        re.VERBOSE | re.MULTILINE,
    )

    re_Table2 = re.compile(r"Table\s'(?P<TABLENO>\d+)'")

    # St. Lucie 6-max Seat #1 is the button
    # Table '1' 9-max Seat #3 is the button
    # Blitz Poker 6-max Seat #1 is the button
    # Table '25' 9-max Seat #8 is the button

    re_HandInfo = re.compile(
        r"""
          ^(?P<TABLE>.+?)\s
          ((?P<MAX>\d+)-max\s)
          (?P<PLAY>\(Play\sMoney\)\s)?
          (Seat\s\#(?P<BUTTON>\d+)\sis\sthe\sbutton)?""",
        re.MULTILINE | re.VERBOSE,
    )

    re_TourneyName1 = re.compile(r"(?P<TOURNAME>.*),\sTable\s\d+")
    re_TourneyName2 = re.compile(r"TN\-(?P<TOURNAME>.+?)\sGAMETYPE")
    re_GTD = re.compile(r"(?P<GTD>[{NUM}]+)\sGTD".format(**substitutions))
    re_buyinType = re.compile(r"\((?P<BUYINTYPE>CAP|Short)\)", re.MULTILINE)
    re_buyin = re.compile("{CUR}(?P<BUYIN>[,.0-9]+)".format(**substitutions), re.MULTILINE)
    re_Step = re.compile(r"\sStep\s(?P<STEPNO>\d+)")

    re_identify = re.compile(r"Game\sID:\s\d+|Hand\s\#\d+\s\-\s")
    re_identify_old = re.compile(r"Game\sID:\s\d+")
    re_SplitHands = re.compile("\n\n")
    re_Button1 = re.compile(r"Seat (?P<BUTTON>\d+) is the button")
    re_Button2 = re.compile(r"Seat #(?P<BUTTON>\d+) is the button")
    re_Board = re.compile(r"\[(?P<CARDS>.+)\]")
    re_TourNo = re.compile(r"\sT(?P<TOURNO>\d+)\-")
    re_File1 = re.compile(r"HH\d{8}\s(T\d+\-)?G\d+")
    re_File2 = re.compile("(?P<TYPE>CASHID|SITGOID|RUSHID|SCHEDULEDID)")

    re_PostSB1 = re.compile(
        r"^Player {PLYR} has small blind \((?P<SB>[{NUM}]+)\)".format(**substitutions),
        re.MULTILINE,
    )
    re_PostBB1 = re.compile(
        r"^Player {PLYR} has big blind \((?P<BB>[{NUM}]+)\)".format(**substitutions),
        re.MULTILINE,
    )
    re_Posts1 = re.compile(
        r"^Player {PLYR} posts \((?P<SBBB>[{NUM}]+)\)".format(**substitutions), re.MULTILINE,
    )
    re_Antes1 = re.compile(
        r"^Player {PLYR} (posts )?ante \((?P<ANTE>[{NUM}]+)\)".format(**substitutions),
        re.MULTILINE,
    )
    re_BringIn1 = re.compile(
        r"^Player {PLYR} bring in \((?P<BRINGIN>[{NUM}]+)\)".format(**substitutions),
        re.MULTILINE,
    )
    re_HeroCards1 = re.compile(
        r"^Player {PLYR} received card: \[(?P<CARD>.+)\]".format(**substitutions),
        re.MULTILINE,
    )

    re_PostSB2 = re.compile(
        r"^{PLYR} posts the small blind {CUR}(?P<SB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_PostBB2 = re.compile(
        r"^{PLYR} posts the big blind {CUR}(?P<BB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_PostBoth2 = re.compile(
        r"^{PLYR} posts dead {CUR}(?P<SBBB>[,.0-9]+)".format(**substitutions), re.MULTILINE,
    )
    re_Posts2 = re.compile(
        r"^{PLYR} posts {CUR}(?P<SBBB>[,.0-9]+)".format(**substitutions), re.MULTILINE,
    )
    re_Antes2 = re.compile(
        r"^{PLYR} posts ante {CUR}(?P<ANTE>[,.0-9]+)".format(**substitutions), re.MULTILINE,
    )
    re_BringIn2 = re.compile(
        r"^{PLYR} brings[- ]in( low|) {CUR}(?P<BRINGIN>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_HeroCards2 = re.compile(
        r"^Dealt to {PLYR}(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(**substitutions),
        re.MULTILINE,
    )
    re_Uncalled = re.compile(
        r"Uncalled bet \({CUR}(?P<BET>[,.\d]+)\) returned to".format(**substitutions),
        re.MULTILINE,
    )

    re_Action1 = re.compile(
        r"""
        ^Player\s({PLYR})?\s(?P<ATYPE>bets|checks|raises|calls|folds|allin|straddle|caps|cap)
        (\s\((?P<BET>[{NUM}]+)\))?
        $""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_Action2 = re.compile(
        r"""
        ^{PLYR}(?P<ATYPE>\sbets|\schecks|\sraises|\scalls|\sfolds|\scaps|\scap|\sstraddle)
        (\s{CUR}(?P<BET>[,.\d]+))?(\sto\s{CUR}(?P<BETTO>[,.\d]+))?
        \s*(and\sis\sall\-in)?\s*$""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    # Player lessthanrocko shows: Two pairs. 8s and 5s [3s 3h]. Bets: 420. Collects: 0. Loses: 420.
    # *Player ChazDazzle shows: Full House (5/8) [7s 5s]. Bets: 420. Collects: 840. Wins: 420.
    # *Player fullstacker shows: Flush, A high [2s 8h 2h Jd] Low hand (A A 2 3 4 8 ).Bets: 0.50. Collects: 0.95. Wins: 0.45.

    # *Player ChazDazzle shows: High card A [6h 10d 2c As 7d 4d 9s] Low hand (A A 2 4 6 7 ).Bets: 3.55. Collects: 3.53. Loses: 0.02.
    # *Player KickAzzJohnny shows: Two pairs. 8s and 3s [5d 3d 3s 6s 8s 8h Ad]. Bets: 3.55. Collects: 3.52. Loses: 0.03.

    re_ShownCards1 = re.compile(
        r"""
        ^\*?Player\s{PLYR}\sshows:\s
        (?P<STRING>.+?)\s
        \[(?P<CARDS>.*)\]
        (\sLow\shand\s\((?P<STRING2>.+?)\s?\))?
        \.""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    # Seat 5: LitAF did not show and won $0.25
    # Seat 6: Thrash370 showed [Td Ad Qd 4s] and won 60600.00 with HI - a straight, Queen high [Qd Jh Td 9d 8d] | LO - [8,5,4,2,1]
    re_ShownCards2 = re.compile(
        r"""
        ^Seat\s(?P<SEAT>[0-9]+):\s{PLYR}\s{BRKTS}
        (?P<SHOWED>showed|mucked)\s\[(?P<CARDS>.+?)\](\sand\s(lost|(won|collected)\s{CUR}(?P<POT>[,\.\d]+))
        \swith (?P<STRING>.+?)
        (,\sand\s(won\s\({CUR}[\.\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?
        $""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_CollectPot1 = re.compile(
        r"""
        ^\*?Player\s{PLYR}\s
        (does\snot\sshow|shows|mucks)
        .+?\.\s?
        Bets:\s[{NUM}]+\.\s
        Collects:\s(?P<POT>[{NUM}]+)\.\s
        (Wins|Loses):\s[{NUM}]+\.?
        $""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    # Seat 5: LitAF did not show and won $0.25
    # Seat 6: Thrash370 showed [Td Ad Qd 4s] and won 60600.00 with HI - a straight, Queen high [Qd Jh Td 9d 8d] | LO - [8,5,4,2,1]
    re_CollectPot2 = re.compile(
        r"""
        Seat\s(?P<SEAT>[0-9]+):\s{PLYR}\s{BRKTS}
        (did\snot\sshow\sand\swon|showed\s\[.+?\]\sand\s(won|collected))\s{CUR}(?P<POT>[,.\d]+)
        (,\smucked|\swith.*|)
        """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    # AssFungus collected $92.25 from main pot 1
    re_CollectPot3 = re.compile(
        r"^{PLYR} collected {CUR}(?P<POT>[,.\d]+)".format(**substitutions), re.MULTILINE,
    )

    def compilePlayerRegexs(self, hand) -> None:
        log.debug(f"compilePlayerRegexs called with hand: {hand}")
        # Implémentation de la méthode

    def readSupportedGames(self):
        return [
            ["ring", "hold", "nl"],
            ["ring", "hold", "fl"],
            ["ring", "hold", "pl"],
            ["ring", "hold", "al"],
            ["ring", "stud", "fl"],
            ["tour", "hold", "nl"],
            ["tour", "hold", "fl"],
            ["tour", "hold", "pl"],
            ["tour", "hold", "al"],
            ["tour", "stud", "fl"],
        ]

    def determineGameType(self, handText):
        log.debug(f"determineGameType called with handText of length: {len(handText)}")

        if self.re_identify_old.search(handText):
            log.debug("Old format identified. Setting version to 1.")
            self.version = 1
            result = self._determineGameType1(handText)
            log.debug(f"Result from _determineGameType1: {result}")
            return result
        log.debug("New format identified. Setting version to 2.")
        self.version = 2
        result = self._determineGameType2(handText)
        log.debug(f"Result from _determineGameType2: {result}")
        return result

    def _determineGameType1(self, handText):
        log.debug("Starting _determineGameType1")
        info = {}

        # Check if the filename matches the expected pattern
        if not self.re_File1.search(self.in_path):
            tmp = f"Invalid filename: {self.in_path}"
            log.debug(f"determine Game Type failed: '{tmp}'")
            raise FpdbHandPartial(tmp)

        # Extract game info from handText
        m = self.re_GameInfo1.search(handText)
        if not m:
            tmp = handText[0:200]
            log.error(f"determine Game Type failed: '{tmp}'")
            raise FpdbParseError

        mg = m.groupdict()
        log.debug(f"Game info extracted: {mg}")

        # Add tournament data if available
        m1 = self.re_TourNo.search(self.in_path)
        if m1:
            mg.update(m1.groupdict())
            log.debug(f"Updated game info with tournament data: {mg}")

        # Extract basic game information
        if "GAME" in mg:
            (info["base"], info["category"]) = self.games1[mg["GAME"]]
            log.debug(f"Base game: {info['base']}, Category: {info['category']}")

        # Extract Small Blind
        if "SB" in mg:
            info["sb"] = mg["SB"]
            log.debug(f"Small Blind: {info['sb']}")

        # Extract Big Blind
        if "BB" in mg:
            info["bb"] = mg["BB"]
            log.debug(f"Big Blind: {info['bb']}")

        # Determine limit type
        if info["base"] == "stud":
            info["limitType"] = "fl"
            log.debug("Limit Type: Fixed Limit (stud)")
        else:
            m2 = self.re_PostBB1.search(handText)
            if m2:
                bb = self.clearMoneyString(m2.group("BB"))
                if Decimal(self.clearMoneyString(info["sb"])) == Decimal(bb):
                    info["limitType"] = "fl"
                    log.debug("Limit Type: Fixed Limit (BB matches SB)")

            if info.get("limitType") is None:
                if "omaha" in info["category"]:
                    info["limitType"] = "pl"
                    log.debug("Limit Type: Pot Limit (omaha)")
                else:
                    info["limitType"] = "nl"
                    log.debug("Limit Type: No Limit")

        # Determine game type: tournament or cash
        if "TOURNO" in mg and mg["TOURNO"] is not None:
            info["type"] = "tour"
        else:
            info["type"] = "ring"
        log.debug(f"Game Type: {info['type']}")

        # Determine currency and buy-in type
        if "TABLE" in mg and mg["TABLE"] is not None:
            if re.match(r"PM\s", mg["TABLE"]):
                info["currency"] = "play"
            elif info["type"] == "tour":
                info["currency"] = "T$"
            else:
                info["currency"] = "USD"
            log.debug(f"Currency: {info['currency']}")

            if "(Cap)" in mg["TABLE"]:
                info["buyinType"] = "cap"
            elif "(Short)" in mg["TABLE"]:
                info["buyinType"] = "shallow"
            else:
                info["buyinType"] = "regular"
            log.debug(f"Buyin Type: {info['buyinType']}")
        else:
            info["currency"] = "T$"
            log.debug("Currency defaulted to T$")

        # Adjust Small Blind and Big Blind for Fixed Limit games
        if info["limitType"] == "fl" and info["bb"] is not None:
            info["sb"] = str((Decimal(mg["SB"]) / 2).quantize(Decimal("0.01")))
            info["bb"] = str(Decimal(mg["SB"]).quantize(Decimal("0.01")))
            log.debug(f"Adjusted SB: {info['sb']}, Adjusted BB: {info['bb']}")

        log.debug(f"Final game info: {info}")
        return info

    def _determineGameType2(self, handText):
        log.debug("Starting _determineGameType2")
        info = {}
        log.debug(f"Input handText: {handText[:200]}...")
        log.debug(f"Attempting regex match with handText: {handText[:200]}")
        m = self.re_GameInfo2.search(handText)
        if not m:
            log.error(f"No match found for handText: {handText[:200]}")
            raise FpdbParseError
        mg = m.groupdict()
        log.debug(f"Regex match groupdict: {mg}")

        m1 = self.re_File2.search(self.in_path)
        if m1:
            mg.update(m1.groupdict())
            log.debug(f"Updated groupdict with file info: {mg}")

        if "LIMIT" in mg:
            info["limitType"] = self.limits[mg["LIMIT"]]
            log.debug(f"Determined limitType: {info['limitType']}")
        if "GAME" in mg:
            (info["base"], info["category"]) = self.games2[mg["GAME"]]
            log.debug(f"Determined base: {info['base']}, category: {info['category']}")
        if "SB" in mg:
            info["sb"] = mg["SB"]
            log.debug(f"Determined small blind (sb): {info['sb']}")
        if "BB" in mg:
            info["bb"] = mg["BB"]
            log.debug(f"Determined big blind (bb): {info['bb']}")
        if "CURRENCY" in mg and mg["CURRENCY"] is not None:
            info["currency"] = self.currencies[mg["CURRENCY"]]
            log.debug(f"Determined currency: {info['currency']}")

        if "TYPE" in mg and mg["TYPE"] == "RUSHID":
            info["fast"] = True
            log.debug("Game type is 'fast'")
        else:
            info["fast"] = False
            log.debug("Game type is not 'fast'")

        if "TOURNO" in mg and mg["TOURNO"] is None:
            info["type"] = "ring"
            log.debug("Game type is 'ring'")
        else:
            info["type"] = "tour"
            log.debug("Game type is 'tour'")

        if info.get("currency") in ("T$", None) and info["type"] == "ring":
            info["currency"] = "play"
            log.debug("Currency set to 'play' for ring games")

        if info["limitType"] == "fl" and info["bb"] is not None:
            info["sb"] = str((Decimal(mg["SB"]) / 2).quantize(Decimal("0.01")))
            info["bb"] = str(Decimal(mg["SB"]).quantize(Decimal("0.01")))
            log.debug(f"Adjusted fixed-limit blinds: sb={info['sb']}, bb={info['bb']}")

        log.debug(f"Final game info: {info}")
        return info

    def readHandInfo(self, hand) -> None:
        log.debug("Starting readHandInfo")
        log.debug(f"Input hand: {hand}")

        if self.version == 1:
            log.debug("Using version 1 for reading hand info")
            self._readHandInfo1(hand)
        else:
            log.debug(f"Using version {self.version} for reading hand info")
            self._readHandInfo2(hand)

        log.debug("Finished readHandInfo")

    def _readHandInfo1(self, hand) -> None:
        log.debug("Starting _readHandInfo1")
        log.debug(
            f"Input handText snippet: {hand.handText[:200]}",
        )  # Display the first 200 characters to avoid verbose logs

        # Check if the hand is cleanly split into pre and post-summary
        if hand.handText.count("------ Summary ------") != 1:
            log.error("Hand is not cleanly split into pre and post Summary")
            msg = "Hand is not cleanly split into pre and post Summary"
            raise FpdbHandPartial(msg)

        info = {}
        log.debug("Attempting to match game and datetime regex")

        # Match game info and datetime regex patterns
        m = self.re_GameInfo1.search(hand.handText)
        m2 = self.re_DateTime1.search(hand.handText)

        if m is None or m2 is None:
            tmp = hand.handText[:200]
            log.error(f"readHandInfo failed: '{tmp}'")
            raise FpdbParseError

        info.update(m.groupdict())
        log.debug(f"GameInfo regex matched: {info}")

        # Match tournament number from the file path
        m1 = self.re_TourNo.search(self.in_path)
        if m1:
            info.update(m1.groupdict())
            log.debug(f"TourNo regex matched: {info}")

        # Parse datetime string and convert to UTC
        datetimestr = "{}/{}/{} {}:{}:{}".format(
            m2.group("Y"),
            m2.group("M"),
            m2.group("D"),
            m2.group("H"),
            m2.group("MIN"),
            m2.group("S"),
        )
        log.debug(f"Parsed datetime string: {datetimestr}")

        hand.startTime = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S")
        hand.startTime = HandHistoryConverter.changeTimezone(
            hand.startTime, self.import_parameters["timezone"], "UTC",
        )
        log.debug(f"Converted startTime: {hand.startTime}")

        # Update main hand info
        if "TOURNO" in info:
            hand.tourNo = info["TOURNO"]
            log.debug(f"Tournament number: {hand.tourNo}")

        if "HID" in info:
            hand.handid = info["HID"]
            log.debug(f"Hand ID: {hand.handid}")

        if "MAX" in info and info["MAX"] is not None:
            hand.maxseats = int(info["MAX"].replace("-max", ""))
            log.debug(f"Max seats from info: {hand.maxseats}")

        # Set default max seats if not defined
        if not hand.maxseats:
            if hand.gametype["base"] == "stud":
                hand.maxseats = 8
            elif hand.gametype["type"] == "ring":
                hand.maxseats = 9
            else:
                hand.maxseats = 10
            log.debug(f"Default max seats set to: {hand.maxseats}")

        # Parse table-specific information
        if "TABLE" in info and info["TABLE"] is not None:
            log.debug(f"Parsing table information: {info['TABLE']}")
            if hand.tourNo:
                # Initialize default tournament values
                hand.buyin = 0
                hand.fee = 0
                hand.buyinCurrency = "NA"
                hand.tablename = 1

                # Match table details
                m3 = self.re_Table1.search(info["TABLE"])
                if m3 is not None:
                    tableinfo = m3.groupdict()
                    log.debug(f"Table regex matched: {tableinfo}")

                    # Process specific table details
                    if "SPECIAL" in tableinfo and tableinfo["SPECIAL"] is not None:
                        log.debug(f"Table special info: {tableinfo['SPECIAL']}")
                        if tableinfo["SPECIAL"] in ("Freeroll", "FREEBUY", "Freebuy"):
                            hand.buyinCurrency = "FREE"
                        hand.guaranteeAmt = int(
                            100 * Decimal(self.clearMoneyString(tableinfo["BUYIN"])),
                        )
                        log.debug(f"Guarantee amount: {hand.guaranteeAmt}")

                    # Process buyin and max seats
                    if hand.guaranteeAmt == 0:
                        hand.buyinCurrency = "USD"
                        hand.buyin = int(
                            100 * Decimal(self.clearMoneyString(tableinfo["BUYIN"])),
                        )
                        log.debug(f"Buyin set to: {hand.buyin} {hand.buyinCurrency}")

                    if "MAX" in tableinfo and tableinfo["MAX"] is not None:
                        n = tableinfo["MAX"].replace("-Max", "")
                        hand.maxseats = 2 if n in ("Heads-up", "Heads-Up") else int(n)
                        log.debug(f"Adjusted max seats: {hand.maxseats}")

                    if "SPEED" in tableinfo and tableinfo["SPEED"] is not None:
                        hand.speed = self.speeds[tableinfo["SPEED"]]
                        log.debug(f"Table speed: {hand.speed}")

                        # Calculate fees for SnG based on speed
                        if hand.maxseats == 2 and hand.buyin in self.HUSnG_Fee:
                            hand.fee = self.HUSnG_Fee[hand.buyin][hand.speed]
                            hand.isSng = True
                        if hand.maxseats != 2 and hand.buyin in self.SnG_Fee:
                            hand.fee = self.SnG_Fee[hand.buyin][hand.speed]
                            hand.isSng = True
                        log.debug(f"SnG fee: {hand.fee}, isSnG: {hand.isSng}")

                    hand.tablename = int(m3.group("TABLENO"))
                    log.debug(f"Table number: {hand.tablename}")

                # Detect specific tournament options
                if "On Demand" in info["TABLE"]:
                    hand.isOnDemand = True
                    log.debug("Table is 'On Demand'")
                if " KO" in info["TABLE"] or "Knockout" in info["TABLE"]:
                    hand.isKO = True
                    log.debug("Table is 'Knockout'")
                if "R/A" in info["TABLE"]:
                    hand.isRebuy = True
                    hand.isAddOn = True
                    log.debug("Table supports Rebuy and Add-On")

                m4 = self.re_TourneyName1.search(info["TABLE"])
                if m4:
                    hand.tourneyName = m4.group("TOURNAME")
                    log.debug(f"Tournament name: {hand.tourneyName}")
            else:
                hand.tablename = info["TABLE"]
                log.debug(f"Table name: {hand.tablename}")

                # Parse buyin type for cash games
                buyin_type = self.re_buyinType.search(info["TABLE"])
                if buyin_type:
                    hand.gametype["buyinType"] = self.buyin[
                        buyin_type.group("BUYINTYPE")
                    ]
                    log.debug(f"Buyin type: {hand.gametype['buyinType']}")
        else:
            # Set default table values for cash games
            hand.buyin = 0
            hand.fee = 0
            hand.buyinCurrency = "NA"
            hand.tablename = 1
            log.debug("Default table settings applied for cash game")

        log.debug("Finished _readHandInfo1")

    def _readHandInfo2(self, hand) -> None:
        log.debug("Starting _readHandInfo2")
        log.debug(
            f"Input handText snippet: {hand.handText[:200]}",
        )  # Display the first 200 characters

        # Check if the hand is cleanly split into pre and post-summary
        if hand.handText.count("*** SUMMARY ***") != 1:
            log.error("Hand is not cleanly split into pre and post Summary")
            msg = "Hand is not cleanly split into pre and post Summary"
            raise FpdbHandPartial(msg)

        info = {}
        log.debug("Attempting to match game and hand info regex patterns")

        # Match game and hand information regex
        m = self.re_GameInfo2.search(hand.handText)
        m1 = self.re_HandInfo.search(hand.handText)

        if m is None or m1 is None:
            tmp = hand.handText[:200]
            log.error(f"read Hand Info failed: '{tmp}'")
            raise FpdbParseError

        info.update(m.groupdict())
        info.update(m1.groupdict())
        log.debug(f"Matched game and hand info: {info}")

        # Process matched info
        for key in info:
            if key == "DATETIME":
                log.debug("Processing DATETIME")
                datetimestr = "2000/01/01 00:00:00"  # Default datetime
                m2 = self.re_DateTime2.finditer(info[key])
                for a in m2:
                    datetimestr = "{}/{}/{} {}:{}:{}".format(
                        a.group("Y"),
                        a.group("M"),
                        a.group("D"),
                        a.group("H"),
                        a.group("MIN"),
                        a.group("S"),
                    )
                hand.startTime = datetime.datetime.strptime(
                    datetimestr, "%Y/%m/%d %H:%M:%S",
                )
                log.debug(f"Parsed startTime: {hand.startTime}")
            if key == "HID":
                hand.handid = info[key]
                log.debug(f"Hand ID: {hand.handid}")
            if key == "TOURNO":
                hand.tourNo = info[key]
                log.debug(f"Tournament number: {hand.tourNo}")
            if key == "LEVEL":
                hand.level = info[key]
                log.debug(f"Tournament level: {hand.level}")
            if key == "TABLE":
                log.debug("Processing TABLE info")
                if info["TOURNO"] is not None:
                    hand.buyin = 0
                    hand.fee = 0
                    hand.buyinCurrency = "FREE"  # Default value for tournaments
                    m2 = self.re_Table2.match(info[key])
                    if m2:
                        hand.tablename = m2.group("TABLENO")
                        log.debug(f"Table number: {hand.tablename}")
                else:
                    hand.tablename = info[key]
                    log.debug(f"Table name: {hand.tablename}")
            if key == "BUTTON":
                hand.buttonpos = info[key]
                log.debug(f"Button position: {hand.buttonpos}")
            if key == "MAX" and info[key] is not None:
                hand.maxseats = int(info[key])
                log.debug(f"Max seats: {hand.maxseats}")

        # Process tournament-specific information
        if "SCHEDULEDID" in self.in_path:
            log.debug("Detected SCHEDULEDID in path")
            m3 = self.re_TourneyName2.search(self.in_path)
            if m3:
                hand.tourneyName = m3.group("TOURNAME").replace("{BACKSLASH}", "\\")
                log.debug(f"Tournament name: {hand.tourneyName}")
                m4 = self.re_GTD.search(hand.tourneyName)
                if m4:
                    hand.isGuarantee = True
                    hand.guaranteeAmt = int(
                        100 * Decimal(self.clearMoneyString(m4.group("GTD"))),
                    )
                    log.debug(f"Guaranteed amount: {hand.guaranteeAmt}")
                if "Satellite" in hand.tourneyName:
                    hand.isSatellite = True
                    log.debug("Tournament is a Satellite")
                if "Shootout" in hand.tourneyName:
                    hand.isShootout = True
                    log.debug("Tournament is a Shootout")

        elif "SITGOID" in self.in_path:
            log.debug("Detected SITGOID in path")
            hand.isSng = True
            m3 = self.re_TourneyName2.search(self.in_path)
            if m3:
                hand.tourneyName = m3.group("TOURNAME").replace("{BACKSLASH}", "\\")
                log.debug(f"Tournament name: {hand.tourneyName}")

                if " Hyper Turbo " in hand.tourneyName:
                    speed = "Hyper Turbo"
                elif " Turbo " in hand.tourneyName:
                    speed = "Turbo"
                else:
                    speed = "Regular"
                hand.speed = self.speeds[speed]
                log.debug(f"Tournament speed: {hand.speed}")

                m4 = self.re_buyin.match(hand.tourneyName)
                if m4:
                    hand.buyinCurrency = "USD"
                    hand.buyin = int(
                        100 * Decimal(self.clearMoneyString(m4.group("BUYIN"))),
                    )
                    log.debug(f"Buyin: {hand.buyin} {hand.buyinCurrency}")

                    if hand.maxseats == 2 and hand.buyin in self.HUSnG_Fee:
                        hand.fee = self.HUSnG_Fee[hand.buyin][hand.speed]
                    if hand.maxseats != 2 and hand.buyin in self.SnG_Fee:
                        hand.fee = self.SnG_Fee[hand.buyin][hand.speed]
                    log.debug(f"Fee: {hand.fee}")

                m5 = self.re_Step.search(hand.tourneyName)
                if m5:
                    hand.isStep = True
                    hand.stepNo = int(m5.group("STEPNO"))
                    log.debug(f"Step number: {hand.stepNo}")

        elif "RUSHID" in self.in_path:
            log.debug("Detected RUSHID in path")
            hand.gametype["fast"], hand.isFast = True, True
            log.debug("Game is fast (Rush)")

        log.debug("Finished _readHandInfo2")

    def readButton(self, hand) -> None:
        if self.version == 1:
            self._readButton1(hand)
        else:
            self._readButton2(hand)

    def _readButton1(self, hand) -> None:
        m = self.re_Button1.search(hand.handText)
        if m:
            hand.buttonpos = int(m.group("BUTTON"))
        else:
            log.info("readButton: not found")

    def _readButton2(self, hand) -> None:
        m = self.re_Button2.search(hand.handText)
        if m:
            hand.buttonpos = int(m.group("BUTTON"))
        else:
            log.info("readButton: not found")

    def readPlayerStacks(self, hand) -> None:
        if self.version == 1:
            self._readPlayerStacks1(hand)
        else:
            self._readPlayerStacks2(hand)

    def _readPlayerStacks1(self, hand) -> None:
        pre, post = hand.handText.split("------ Summary ------")
        m = self.re_PlayerInfo1.finditer(pre)
        for a in m:
            hand.addPlayer(
                int(a.group("SEAT")),
                a.group("PNAME"),
                self.clearMoneyString(a.group("CASH")),
            )

    def _readPlayerStacks2(self, hand) -> None:
        pre, post = hand.handText.split("*** SUMMARY ***")
        m = self.re_PlayerInfo2.finditer(pre)
        for a in m:
            hand.addPlayer(
                int(a.group("SEAT")),
                a.group("PNAME"),
                self.clearMoneyString(a.group("CASH")),
            )

    def markStreets(self, hand) -> None:
        if self.version == 1:
            self._markStreets1(hand)
        else:
            self._markStreets2(hand)

    def _markStreets1(self, hand) -> None:
        log.debug("Starting _markStreets1")
        log.debug(f"Game type base: {hand.gametype['base']}")
        if hand.gametype["base"] in ("hold"):
            log.debug("Attempting to match streets for hold'em game")
            m = re.search(
                r"(?P<PREFLOP>.+(?=\*\*\* FLOP \*\*\*:)|.+)"
                r"(\*\*\* FLOP \*\*\*:(?P<FLOP> (\[\S\S\S?] )?\[\S\S\S? ?\S\S\S? \S\S\S?].+(?=\*\*\* TURN \*\*\*:)|.+))?"
                r"(\*\*\* TURN \*\*\*: \[\S\S\S? \S\S\S? \S\S\S?] (?P<TURN>\[\S\S\S?\].+(?=\*\*\* RIVER \*\*\*:)|.+))?"
                r"(\*\*\* RIVER \*\*\*: \[\S\S\S? \S\S\S? \S\S\S? \S\S\S?] ?(?P<RIVER>\[\S\S\S?\].+))?",
                hand.handText,
                re.DOTALL,
            )
        elif hand.gametype["base"] in ("stud"):
            log.debug("Attempting to match streets for stud game")
            m = re.search(
                r"(?P<THIRD>.+(?=\*\*\* Third street \*\*\*)|.+)"
                r"(\*\*\* Third street \*\*\*(?P<FOURTH>.+(?=\*\*\* Fourth street \*\*\*)|.+))?"
                r"(\*\*\* Fourth street \*\*\*(?P<FIFTH>.+(?=\*\*\* Fifth street \*\*\*)|.+))?"
                r"(\*\*\* Fifth street \*\*\*(?P<SIXTH>.+(?=\*\*\* Sixth street \*\*\*)|.+))?"
                r"(\*\*\* Sixth street \*\*\*(?P<SEVENTH>.+))?",
                hand.handText,
                re.DOTALL,
            )
        else:
            log.warning("Unknown game type base, streets matching skipped")
            return
        if m:
            log.debug("Streets successfully matched")
        else:
            log.warning("No streets matched")
        hand.addStreets(m)
        log.debug("Finished _markStreets1")

    def _markStreets2(self, hand) -> None:
        log.debug("Starting _markStreets2")
        log.debug(f"Game type base: {hand.gametype['base']}")
        if hand.gametype["base"] in ("hold"):
            log.debug("Attempting to match streets for hold'em game")
            m = re.search(
                r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>(.+(?P<FLOPET>\[\S\S\]))?.+(?=\*\*\* (FLOP|FIRST FLOP|FLOP 1) \*\*\*)|.+)"
                r"(\*\*\* FLOP \*\*\*(?P<FLOP> (\[\S\S\] )?\[(\S\S ?)?\S\S \S\S\].+(?=\*\*\* (TURN|FIRST TURN|TURN 1) \*\*\*)|.+))?"
                r"(\*\*\* TURN \*\*\* \[\S\S \S\S \S\S] (?P<TURN>\[\S\S\].+(?=\*\*\* (RIVER|FIRST RIVER|RIVER 1) \*\*\*)|.+))?"
                r"(\*\*\* RIVER \*\*\* \[\S\S \S\S \S\S \S\S] (?P<RIVER>\[\S\S\].+))?"
                r"(\*\*\* (FIRST FLOP|FLOP 1) \*\*\*(?P<FLOP1> (\[\S\S\] )?\[(\S\S ?)?\S\S \S\S\].+(?=\*\*\* (FIRST TURN|TURN 1) \*\*\*)|.+))?"
                r"(\*\*\* (FIRST TURN|TURN 1) \*\*\* \[\S\S \S\S \S\S] (?P<TURN1>\[\S\S\].+(?=\*\*\* (FIRST RIVER|RIVER 1) \*\*\*)|.+))?"
                r"(\*\*\* (FIRST RIVER|RIVER 1) \*\*\* \[\S\S \S\S \S\S \S\S] (?P<RIVER1>\[\S\S\].+?(?=\*\*\* (SECOND (FLOP|TURN|RIVER)|(FLOP|TURN|RIVER) 2) \*\*\*)|.+))?"
                r"(\*\*\* (SECOND FLOP|FLOP 2) \*\*\*(?P<FLOP2> (\[\S\S\] )?\[\S\S ?\S\S \S\S\].+(?=\*\*\* (SECOND TURN|TURN 2) \*\*\*)|.+))?"
                r"(\*\*\* (SECOND TURN|TURN 2) \*\*\* \[\S\S \S\S \S\S] (?P<TURN2>\[\S\S\].+(?=\*\*\* (SECOND RIVER|RIVER 2) \*\*\*)|.+))?"
                r"(\*\*\* (SECOND RIVER|RIVER 2) \*\*\* \[\S\S \S\S \S\S \S\S] (?P<RIVER2>\[\S\S\].+))?",
                hand.handText,
                re.DOTALL,
            )
        elif hand.gametype["base"] in ("stud"):
            log.debug("Attempting to match streets for stud game")
            m = re.search(
                r"(?P<ANTES>.+(?=\*\*\* 3rd STREET \*\*\*)|.+)"
                r"(\*\*\* 3rd STREET \*\*\*(?P<THIRD>.+(?=\*\*\* 4th STREET \*\*\*)|.+))?"
                r"(\*\*\* 4th STREET \*\*\*(?P<FOURTH>.+(?=\*\*\* 5th STREET \*\*\*)|.+))?"
                r"(\*\*\* 5th STREET \*\*\*(?P<FIFTH>.+(?=\*\*\* 6th STREET \*\*\*)|.+))?"
                r"(\*\*\* 6th STREET \*\*\*(?P<SIXTH>.+(?=\*\*\* 7th STREET \*\*\*)|.+))?"
                r"(\*\*\* 7th STREET \*\*\*(?P<SEVENTH>.+))?",
                hand.handText,
                re.DOTALL,
            )
        else:
            log.warning("Unknown game type base, streets matching skipped")
            return
        if m:
            log.debug("Streets successfully matched")
        else:
            log.warning("No streets matched")
        hand.addStreets(m)
        log.debug("Finished _markStreets2")

    def readCommunityCards(self, hand, street) -> None:
        log.debug("Starting readCommunityCards")
        log.debug(f"Processing street: {street}, Hand ID: {hand.handid}")
        if self.version == 1:
            self._readCommunityCards1(hand, street)
        else:
            self._readCommunityCards2(hand, street)
        if street in ("FLOP1", "TURN1", "RIVER1", "FLOP2", "TURN2", "RIVER2"):
            hand.runItTimes = 2
            log.debug(f"Set runItTimes to 2 for street: {street}")
        log.debug("Finished readCommunityCards")

    def _readCommunityCards1(self, hand, street) -> None:
        log.debug(f"Executing _readCommunityCards1 for street: {street}")
        m = self.re_Board.search(hand.streets[street])
        if m:
            cards = [c.replace("10", "T") for c in m.group("CARDS").split(" ")]
            hand.setCommunityCards(street, cards)
            log.debug(f"Set community cards for {street}: {cards}")
        else:
            log.error(f"No community cards found on {street}, Hand ID: {hand.handid}")
            raise FpdbParseError

    def _readCommunityCards2(self, hand, street) -> None:
        log.debug(f"Executing _readCommunityCards2 for street: {street}")
        m = self.re_Board.search(hand.streets[street])
        if m:
            cards = m.group("CARDS").split(" ")
            hand.setCommunityCards(street, cards)
            log.debug(f"Set community cards for {street}: {cards}")
        else:
            log.error(f"No community cards found on {street}, Hand ID: {hand.handid}")
            raise FpdbParseError

    def readAntes(self, hand) -> None:
        log.debug("Starting readAntes")
        log.debug(f"Hand ID: {hand.handid}, Version: {self.version}")
        if self.version == 1:
            self._readAntes1(hand)
        else:
            self._readAntes2(hand)
        log.debug("Finished readAntes")

    def _readAntes1(self, hand) -> None:
        log.debug("Executing _readAntes1")
        m = self.re_Antes1.finditer(hand.handText)
        for player in m:
            pname = player.group("PNAME")
            ante = player.group("ANTE")
            hand.addAnte(pname, ante)
            log.debug(f"Added ante for player: {pname}, Ante: {ante}")

    def _readAntes2(self, hand) -> None:
        log.debug("Executing _readAntes2")
        m = self.re_Antes2.finditer(hand.handText)
        for player in m:
            pname = player.group("PNAME")
            ante = player.group("ANTE")
            hand.addAnte(pname, ante)
            log.debug(f"Added ante for player: {pname}, Ante: {ante}")

    def readBringIn(self, hand) -> None:
        log.debug("Starting readBringIn")
        log.debug(f"Hand ID: {hand.handid}, Version: {self.version}")
        if self.version == 1:
            self._readBringIn1(hand)
        else:
            self._readBringIn2(hand)
        log.debug("Finished readBringIn")

    def _readBringIn1(self, hand) -> None:
        log.debug("Executing _readBringIn1")
        m = self.re_BringIn1.search(hand.handText, re.DOTALL)
        if m:
            pname = m.group("PNAME")
            bringin = m.group("BRINGIN")
            hand.addBringIn(pname, bringin)
            log.debug(f"Added bring-in for player: {pname}, Bring-in: {bringin}")
        else:
            log.debug("No bring-in found in _readBringIn1")

    def _readBringIn2(self, hand) -> None:
        log.debug("Executing _readBringIn2")
        m = self.re_BringIn2.search(hand.handText, re.DOTALL)
        if m:
            pname = m.group("PNAME")
            bringin = m.group("BRINGIN")
            hand.addBringIn(pname, bringin)
            log.debug(f"Added bring-in for player: {pname}, Bring-in: {bringin}")
        else:
            log.debug("No bring-in found in _readBringIn2")

    def readBlinds(self, hand) -> None:
        log.debug("Starting readBlinds")
        log.debug(f"Hand ID: {hand.handid}, Version: {self.version}")
        if self.version == 1:
            self._readBlinds1(hand)
        else:
            self._readBlinds2(hand)
        log.debug("Finished readBlinds")

    def _readBlinds1(self, hand) -> None:
        log.debug("Executing _readBlinds1")
        liveBlind = True
        for a in self.re_PostSB1.finditer(hand.handText):
            pname = a.group("PNAME")
            sb = a.group("SB")
            if liveBlind:
                hand.addBlind(pname, "small blind", sb)
                log.debug(f"Added live small blind for player: {pname}, Amount: {sb}")
                liveBlind = False
            else:
                log.debug(f"Skipped dead small blind for player: {pname}, Amount: {sb}")
        for a in self.re_PostBB1.finditer(hand.handText):
            pname = a.group("PNAME")
            bb = a.group("BB")
            hand.addBlind(pname, "big blind", bb)
            log.debug(f"Added big blind for player: {pname}, Amount: {bb}")
        for a in self.re_Posts1.finditer(hand.handText):
            pname = a.group("PNAME")
            sbbb = self.clearMoneyString(a.group("SBBB"))
            if Decimal(sbbb) == Decimal(hand.bb):
                hand.addBlind(pname, "big blind", sbbb)
                log.debug(f"Added big blind for player: {pname}, Amount: {sbbb}")
            else:
                hand.addBlind(pname, "secondsb", sbbb)
                log.debug(
                    f"Added second small blind for player: {pname}, Amount: {sbbb}",
                )

    def _readBlinds2(self, hand) -> None:
        log.debug("Executing _readBlinds2")
        liveBlind = True
        for a in self.re_PostSB2.finditer(hand.handText):
            pname = a.group("PNAME")
            sb = a.group("SB")
            if liveBlind:
                hand.addBlind(pname, "small blind", sb)
                log.debug(f"Added live small blind for player: {pname}, Amount: {sb}")
                liveBlind = False
            else:
                log.debug(f"Skipped dead small blind for player: {pname}, Amount: {sb}")
        for a in self.re_PostBB2.finditer(hand.handText):
            pname = a.group("PNAME")
            bb = a.group("BB")
            hand.addBlind(pname, "big blind", bb)
            log.debug(f"Added big blind for player: {pname}, Amount: {bb}")
        for a in self.re_PostBoth2.finditer(hand.handText):
            pname = a.group("PNAME")
            both = self.clearMoneyString(a.group("SBBB"))
            hand.addBlind(pname, "both", both)
            log.debug(f"Added both blinds for player: {pname}, Amount: {both}")
        for a in self.re_Posts2.finditer(hand.handText):
            pname = a.group("PNAME")
            sbbb = self.clearMoneyString(a.group("SBBB"))
            if Decimal(sbbb) == Decimal(hand.bb):
                hand.addBlind(pname, "big blind", sbbb)
                log.debug(f"Added big blind for player: {pname}, Amount: {sbbb}")
            else:
                hand.addBlind(pname, "secondsb", sbbb)
                log.debug(
                    f"Added second small blind for player: {pname}, Amount: {sbbb}",
                )

    def readHoleCards(self, hand) -> None:
        log.debug("Starting readHoleCards")
        log.debug(f"Hand ID: {hand.handid}, Version: {self.version}")
        if self.version == 1:
            self._readHoleCards1(hand)
        else:
            self._readHoleCards2(hand)
        log.debug("Finished readHoleCards")

    def _readHoleCards1(self, hand) -> None:
        log.debug("Executing _readHoleCards1")
        # Streets PREFLOP, PREDRAW, and THIRD are special cases because
        # we need to grab hero's cards
        for street in ("PREFLOP", "DEAL"):
            if street in hand.streets:
                log.debug(f"Processing street: {street}")
                newcards = []
                m = self.re_HeroCards1.finditer(hand.streets[street])
                for found in m:
                    hand.hero = found.group("PNAME")
                    card = found.group("CARD").replace("10", "T")
                    newcards.append(card)
                    log.debug(f"Found card for hero: {card}, Player: {hand.hero}")
                if hand.hero:
                    hand.addHoleCards(
                        street,
                        hand.hero,
                        closed=newcards,
                        shown=False,
                        mucked=False,
                        dealt=True,
                    )
                    log.debug(f"Added hole cards for hero on {street}: {newcards}")

        for street, text in list(hand.streets.items()):
            if not text or street in ("PREFLOP", "DEAL"):
                continue  # already processed these
            log.debug(f"Processing street: {street}")
            m = self.re_HeroCards1.finditer(hand.streets[street])
            players = {}
            for found in m:
                player = found.group("PNAME")
                card = found.group("CARD").replace("10", "T")
                if players.get(player) is None:
                    players[player] = []
                players[player].append(card)
                log.debug(f"Found card for player: {card}, Player: {player}")

            for player, cards in list(players.items()):
                log.debug(f"Processing player: {player}, Cards: {cards}")
                if street == "THIRD":  # hero in stud game
                    hand.dealt.add(player)  # Need this for stud?
                    if len(cards) == 3:
                        hand.hero = player
                        hand.addHoleCards(
                            street,
                            player,
                            closed=cards[0:2],
                            open=[cards[2]],
                            shown=False,
                            mucked=False,
                            dealt=False,
                        )
                        log.debug(
                            f"Added hole cards for hero in stud game: Closed={cards[0:2]}, Open={cards[2:]}",
                        )
                    else:
                        hand.addHoleCards(
                            street,
                            player,
                            closed=[],
                            open=cards,
                            shown=False,
                            mucked=False,
                            dealt=False,
                        )
                        log.debug(f"Added hole cards for player: Open={cards}")
                elif street == "SEVENTH":
                    if hand.hero == player:
                        hand.addHoleCards(
                            street,
                            player,
                            open=cards,
                            closed=[],
                            shown=False,
                            mucked=False,
                            dealt=False,
                        )
                        log.debug(f"Added open cards for hero on {street}: {cards}")
                    else:
                        hand.addHoleCards(
                            street,
                            player,
                            open=[],
                            closed=cards,
                            shown=False,
                            mucked=False,
                            dealt=False,
                        )
                        log.debug(f"Added closed cards for player on {street}: {cards}")
                else:
                    hand.addHoleCards(
                        street,
                        player,
                        open=cards,
                        closed=[],
                        shown=False,
                        mucked=False,
                        dealt=False,
                    )
                    log.debug(f"Added open cards for player on {street}: {cards}")

    def _readHoleCards2(self, hand) -> None:
        log.debug("Executing _readHoleCards2")
        # Streets PREFLOP, PREDRAW, and THIRD are special cases because
        # we need to grab hero's cards
        for street in ("PREFLOP", "DEAL"):
            if street in hand.streets:
                log.debug(f"Processing street: {street}")
                newcards = []
                m = self.re_HeroCards2.finditer(hand.streets[street])
                for found in m:
                    hand.hero = found.group("PNAME")
                    newcards = found.group("NEWCARDS").split(" ")
                    log.debug(f"Found cards for hero: {newcards}, Player: {hand.hero}")
                if hand.hero:
                    hand.addHoleCards(
                        street,
                        hand.hero,
                        closed=newcards,
                        shown=False,
                        mucked=False,
                        dealt=True,
                    )
                    log.debug(f"Added hole cards for hero on {street}: {newcards}")

        for street, text in list(hand.streets.items()):
            if not text or street in ("PREFLOP", "DEAL"):
                continue  # already processed these
            log.debug(f"Processing street: {street}")
            m = self.re_HeroCards2.finditer(hand.streets[street])
            for found in m:
                player = found.group("PNAME")
                newcards = (
                    found.group("NEWCARDS").split(" ")
                    if found.group("NEWCARDS")
                    else []
                )
                oldcards = (
                    found.group("OLDCARDS").split(" ")
                    if found.group("OLDCARDS")
                    else []
                )
                log.debug(
                    f"Player: {player}, New cards: {newcards}, Old cards: {oldcards}",
                )

                if street == "THIRD" and len(newcards) == 3:  # hero in stud game
                    hand.hero = player
                    hand.dealt.add(player)  # Need this for stud?
                    hand.addHoleCards(
                        street,
                        player,
                        closed=newcards[0:2],
                        open=[newcards[2]],
                        shown=False,
                        mucked=False,
                        dealt=False,
                    )
                    log.debug(
                        f"Added hole cards for hero in stud game: Closed={newcards[0:2]}, Open={newcards[2:]}",
                    )
                else:
                    hand.addHoleCards(
                        street,
                        player,
                        open=newcards,
                        closed=oldcards,
                        shown=False,
                        mucked=False,
                        dealt=False,
                    )
                    log.debug(
                        f"Added hole cards for player on {street}: Open={newcards}, Closed={oldcards}",
                    )

    def readAction(self, hand, street) -> None:
        log.debug("Starting readAction")
        log.debug(
            f"Processing street: {street}, Hand ID: {hand.handid}, Version: {self.version}",
        )
        if self.version == 1:
            self._readAction1(hand, street)
        else:
            self._readAction2(hand, street)
        log.debug("Finished readAction")

    def _readAction1(self, hand, street) -> None:
        log.debug(f"Executing _readAction1 for street: {street}")
        m = self.re_Action1.finditer(hand.streets[street])
        for action in m:
            action_details = action.groupdict()
            log.debug(f"Action details: {action_details}")
            if action.group("PNAME") is None:
                log.error(
                    f"Unknown player in action: {action.group('ATYPE')}, Hand ID: {hand.handid}",
                )
                raise FpdbParseError

            player = action.group("PNAME")
            action_type = action.group("ATYPE")
            log.debug(f"Processing action: {action_type}, Player: {player}")

            if action_type == "folds":
                hand.addFold(street, player)
                log.debug(f"Added fold action: Player={player}, Street={street}")
            elif action_type == "checks":
                hand.addCheck(street, player)
                log.debug(f"Added check action: Player={player}, Street={street}")
            elif action_type == "calls":
                amount = self.clearMoneyString(action.group("BET"))
                hand.addCall(street, player, amount)
                log.debug(
                    f"Added call action: Player={player}, Amount={amount}, Street={street}",
                )
            elif action_type in ("raises", "straddle", "caps", "cap"):
                amount = self.clearMoneyString(action.group("BET"))
                hand.addCallandRaise(street, player, amount)
                log.debug(
                    f"Added raise action: Player={player}, Amount={amount}, Street={street}",
                )
            elif action_type == "bets":
                amount = self.clearMoneyString(action.group("BET"))
                hand.addBet(street, player, amount)
                log.debug(
                    f"Added bet action: Player={player}, Amount={amount}, Street={street}",
                )
            elif action_type == "allin":
                # Handle all-in action
                log.debug(f"Processing all-in action: Player={player}")
                if action.group("BET") is None:
                    amount = str(hand.stacks[player])
                    log.debug(f"Disconnected all-in, using player's stack: {amount}")
                else:
                    amount = self.clearMoneyString(action.group("BET")).replace(
                        ",", "",
                    )  # Some sites use commas
                    log.debug(f"All-in amount: {amount}")

                Ai = Decimal(amount)
                Bp = hand.lastBet[street]
                Bc = sum(hand.bets[street][player])
                C = Bp - Bc
                log.debug(f"All-in calculation: Ai={Ai}, Bp={Bp}, Bc={Bc}, C={C}")

                if Ai <= C:
                    hand.addCall(street, player, amount)
                    log.debug(
                        f"Added all-in as call: Player={player}, Amount={amount}, Street={street}",
                    )
                elif Bp == 0:
                    hand.addBet(street, player, amount)
                    log.debug(
                        f"Added all-in as bet: Player={player}, Amount={amount}, Street={street}",
                    )
                else:
                    hand.addCallandRaise(street, player, amount)
                    log.debug(
                        f"Added all-in as call and raise: Player={player}, Amount={amount}, Street={street}",
                    )
            else:
                log.debug(
                    f"Unimplemented action type: '{action_type}' for Player: '{player}'",
                )

    def _readAction2(self, hand, street) -> None:
        log.debug(f"Executing _readAction2 for street: {street}")
        m = self.re_Action2.finditer(hand.streets[street])
        for action in m:
            action_details = action.groupdict()
            log.debug(f"Action details: {action_details}")

            player = action.group("PNAME")
            action_type = action.group("ATYPE").strip()
            log.debug(f"Processing action: {action_type}, Player: {player}")

            if action_type == "folds":
                hand.addFold(street, player)
                log.debug(f"Added fold action: Player={player}, Street={street}")
            elif action_type == "checks":
                hand.addCheck(street, player)
                log.debug(f"Added check action: Player={player}, Street={street}")
            elif action_type == "calls":
                amount = self.clearMoneyString(action.group("BET"))
                hand.addCall(street, player, amount)
                log.debug(
                    f"Added call action: Player={player}, Amount={amount}, Street={street}",
                )
            elif action_type in ("raises", "straddle", "caps", "cap"):
                if action.group("BETTO") is not None:
                    amount_to = self.clearMoneyString(action.group("BETTO"))
                    hand.addRaiseTo(street, player, amount_to)
                    log.debug(
                        f"Added raise-to action: Player={player}, AmountTo={amount_to}, Street={street}",
                    )
                elif action.group("BET") is not None:
                    amount = self.clearMoneyString(action.group("BET"))
                    hand.addCallandRaise(street, player, amount)
                    log.debug(
                        f"Added call and raise action: Player={player}, Amount={amount}, Street={street}",
                    )
            elif action_type == "bets":
                amount = self.clearMoneyString(action.group("BET"))
                hand.addBet(street, player, amount)
                log.debug(
                    f"Added bet action: Player={player}, Amount={amount}, Street={street}",
                )
            else:
                log.debug(f"Unimplemented action: '{player}' '{action_type}'")

    def readCollectPot(self, hand) -> None:
        log.debug("Starting readCollectPot")
        log.debug(
            f"Hand ID: {hand.handid}, Version: {self.version}, Run It Times: {getattr(hand, 'runItTimes', 1)}",
        )
        if self.version == 1:
            self._readCollectPot1(hand)
        elif hand.runItTimes == 2:
            self._readCollectPot3(hand)
        else:
            self._readCollectPot2(hand)
        log.debug("Finished readCollectPot")

    def _readCollectPot1(self, hand) -> None:
        log.debug("Executing _readCollectPot1")
        for m in self.re_CollectPot1.finditer(hand.handText):
            pot_amount = Decimal(self.clearMoneyString(m.group("POT")))
            if pot_amount > 0:
                player = m.group("PNAME")
                hand.addCollectPot(player=player, pot=m.group("POT"))
                log.debug(f"Added collected pot: Player={player}, Pot={pot_amount}")
            else:
                log.debug(
                    f"Ignored pot collection with zero or negative amount: {m.group('POT')}",
                )

    def _readCollectPot2(self, hand) -> None:
        log.debug("Executing _readCollectPot2")
        try:
            pre, post = hand.handText.split("*** SUMMARY ***")
            log.debug("Successfully split handText into pre and post summary sections")
            acts = hand.actions.get("PREFLOP")
            bovadaUncalled_v1 = False
            bovadaUncalled_v2 = False
            blindsantes = 0
            adjustment = 0

            if acts is not None and len([a for a in acts if a[1] != "folds"]) == 0:
                log.debug("All actions in PREFLOP are folds, checking uncalled bets")
                m0 = self.re_Uncalled.search(hand.handText)
                if m0 and Decimal(m0.group("BET")) == Decimal(hand.bb):
                    bovadaUncalled_v2 = True
                    log.debug("Detected Bovada uncalled bet version 2")
                elif m0 is None:
                    bovadaUncalled_v1 = True
                    log.debug("Detected Bovada uncalled bet version 1")
                    has_sb = (
                        len(
                            [
                                a[2]
                                for a in hand.actions.get("BLINDSANTES")
                                if a[1] == "small blind"
                            ],
                        )
                        > 0
                    )
                    adjustment = (
                        (Decimal(hand.bb) - Decimal(hand.sb))
                        if has_sb
                        else Decimal(hand.bb)
                    )
                    blindsantes = sum([a[2] for a in hand.actions.get("BLINDSANTES")])
                    log.debug(
                        f"Adjustment calculated: {adjustment}, Blinds/Antes total: {blindsantes}",
                    )
            else:
                log.debug(
                    "Not all actions in PREFLOP are folds, checking for uncalled bets",
                )
                m0 = self.re_Uncalled.search(hand.handText)
                if not m0:
                    hand.setUncalledBets(True)
                    log.debug("Set uncalled bets to True")

            for m in self.re_CollectPot2.finditer(post):
                pot = self.clearMoneyString(m.group("POT"))
                player = m.group("PNAME")
                log.debug(f"Processing pot collection: Player={player}, Pot={pot}")
                if bovadaUncalled_v1 and Decimal(pot) == blindsantes:
                    adjusted_pot = str(Decimal(pot) - adjustment)
                    hand.addCollectPot(player=player, pot=adjusted_pot)
                    log.debug(
                        f"Adjusted pot for Bovada version 1: Player={player}, Adjusted Pot={adjusted_pot}",
                    )
                elif bovadaUncalled_v2:
                    doubled_pot = str(Decimal(pot) * 2)
                    hand.addCollectPot(player=player, pot=doubled_pot)
                    log.debug(
                        f"Doubled pot for Bovada version 2: Player={player}, Doubled Pot={doubled_pot}",
                    )
                else:
                    hand.addCollectPot(player=player, pot=pot)
                    log.debug(
                        f"Added regular pot collection: Player={player}, Pot={pot}",
                    )
        except Exception as e:
            log.exception(f"Error in _readCollectPot2: {e}")
            raise

    def _readCollectPot3(self, hand) -> None:
        log.debug("Executing _readCollectPot3")
        for m in self.re_CollectPot3.finditer(hand.handText):
            player = m.group("PNAME")
            pot = m.group("POT")
            hand.addCollectPot(player=player, pot=pot)
            log.debug(f"Added pot collection for Player={player}, Pot={pot}")

    def readShowdownActions(self, hand) -> None:
        log.debug(f"Starting readShowdownActions for Hand ID: {hand.handid}")
        # TODO: Implement logic for showdown actions
        log.debug("Showdown actions functionality not yet implemented")

    def readSTP(self, hand) -> None:
        log.debug(f"Starting readSTP for Hand ID: {hand.handid}")
        log.warning(f"STP functionality not implemented for Hand ID: {hand.handid}")

    def readTourneyResults(self, hand) -> None:
        log.debug(f"Starting readTourneyResults for Hand ID: {hand.handid}")
        log.info("Reading tournament result info for Winamax.")
        # TODO: Implement tournament results reading logic

    def readShownCards(self, hand) -> None:
        log.debug("Starting readShownCards")
        log.debug(f"Hand ID: {hand.handid}, Version: {self.version}")
        if self.version == 1:
            self._readShownCards1(hand)
            log.debug("Executed _readShownCards1")
        else:
            self._readShownCards2(hand)
            log.debug("Executed _readShownCards2")

    def _readShownCards1(self, hand) -> None:
        log.debug("Executing _readShownCards1")
        for m in self.re_ShownCards1.finditer(hand.handText):
            if m.group("CARDS") is not None:
                cards = m.group("CARDS")
                cards = [
                    c.replace("10", "T") for c in cards.split(" ")
                ]  # needs to be a list, not a set--stud needs the order
                string = m.group("STRING")
                if m.group("STRING2"):
                    string += "|" + m.group("STRING2")

                (shown, mucked) = (False, False)
                # Uncomment and modify based on additional logic
                # if m.group('SHOWED') == "showed": shown = True
                # elif m.group('SHOWED') == "mucked": mucked = True

                log.debug(
                    f"Adding shown cards: Cards={cards}, Player={m.group('PNAME')}, "
                    f"Shown={shown}, Mucked={mucked}, String={string}",
                )
                hand.addShownCards(
                    cards=cards,
                    player=m.group("PNAME"),
                    shown=shown,
                    mucked=mucked,
                    string=string,
                )
            else:
                log.debug("No cards found in _readShownCards1 for current match")

    def _readShownCards2(self, hand) -> None:
        log.debug("Executing _readShownCards2")
        for m in self.re_ShownCards2.finditer(hand.handText):
            if m.group("CARDS") is not None:
                cards = m.group("CARDS").split(
                    " ",
                )  # needs to be a list, not a set--stud needs the order
                string = m.group("STRING")
                if m.group("STRING2"):
                    string += "|" + m.group("STRING2")

                (shown, mucked) = (False, False)
                if m.group("SHOWED") == "showed":
                    shown = True
                elif m.group("SHOWED") == "mucked":
                    mucked = True

                log.debug(
                    f"Adding shown cards: Cards={cards}, Player={m.group('PNAME')}, "
                    f"Shown={shown}, Mucked={mucked}, String={string}",
                )
                hand.addShownCards(
                    cards=cards,
                    player=m.group("PNAME"),
                    shown=shown,
                    mucked=mucked,
                    string=string,
                )
            else:
                log.debug("No cards found in _readShownCards2 for current match")

    def readSummaryInfo(self, summaryInfoList) -> bool:
        log.info("Entering method readSummaryInfo")
        log.debug(f"Summary Info List: {summaryInfoList}")
        log.debug("Method readSummaryInfo not implemented.")
        return True

    @staticmethod
    def getTableTitleRe(type, table_name=None, tournament=None, table_number=None):
        """Returns string to search in windows titles."""
        log.debug("Executing getTableTitleRe")
        log.debug(
            f"Parameters received: type='{type}', table_name='{table_name}', "
            f"tournament='{tournament}', table_number='{table_number}'",
        )

        regex = re.escape(str(table_name))
        if type == "tour":
            regex = (
                ", Table "
                + re.escape(str(table_number))
                + r"\s\-.*\s\("
                + re.escape(str(tournament))
                + r"\)"
            )
            log.debug(f"Constructed regex for tournament: '{regex}'")
        else:
            log.debug(f"Constructed regex for non-tournament table: '{regex}'")

        log.info(f"Generated Table Title regex: '{regex}'")
        return regex


    def readOther(self, hand: "Hand") -> None:
        """Read other information from hand that doesn't fit standard categories.

        Args:
            hand: The Hand object to read other information from.

        Returns:
            None

        """