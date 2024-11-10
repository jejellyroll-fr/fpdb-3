#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#    Copyright 2009-2011, Grigorij Indigirkin
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

from HandHistoryConverter import HandHistoryConverter, FpdbParseError, FpdbHandPartial
from decimal import Decimal
import re
import logging
import datetime
import time

# PartyPoker HH Format
log = logging.getLogger("parser")


class PartyPoker(HandHistoryConverter):
    sitename = "PartyPoker"
    codepage = ("utf8", "cp1252")
    siteId = 9
    filetype = "text"
    sym = {"USD": "\$", "EUR": "\u20ac", "T$": "", "play": "play"}
    currencies = {"\$": "USD", "$": "USD", "\xe2\x82\xac": "EUR", "\u20ac": "EUR", "": "T$", "play": "play"}
    substitutions = {
        "LEGAL_ISO": "USD|EUR",  # legal ISO currency codes
        "LS": "\$|\u20ac|\xe2\x82\xac|",  # Currency symbols - Euro(cp1252, utf-8)
        "NUM": ".,'\dKMB",
    }
    limits = {"NL": "nl", "PL": "pl", "": "fl", "FL": "fl", "Limit": "fl"}
    games = {  # base, category
        "Texas Hold'em": ("hold", "holdem"),
        "Texas Holdem": ("hold", "holdem"),
        "Hold'em": ("hold", "holdem"),
        "Holdem": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi": ("hold", "omahahi"),
        "Omaha Hi-Lo": ("hold", "omahahilo"),
        "7 Card Stud Hi-Lo": ("stud", "studhilo"),
        "7 Card Stud": ("stud", "studhi"),
        "Double Hold'em": ("hold", "2_holdem"),
        "Double Holdem": ("hold", "2_holdem"),
        "Short Deck": ("hold", "6_holdem"),
    }

    Lim_Blinds = {
        "0.04": ("0.01", "0.02"),
        "0.08": ("0.02", "0.04"),
        "0.10": ("0.02", "0.05"),
        "0.20": ("0.05", "0.10"),
        "0.30": ("0.07", "0.15"),
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
        "12.00": ("3.00", "6.00"),
        "12": ("3.00", "6.00"),
        "20.00": ("5.00", "10.00"),
        "20": ("5.00", "10.00"),
        "30.00": ("10.00", "15.00"),
        "30": ("10.00", "15.00"),
        "40.00": ("10.00", "20.00"),
        "40": ("10.00", "20.00"),
        "50.00": ("10.00", "25.00"),
        "50": ("10.00", "25.00"),
        "60.00": ("15.00", "30.00"),
        "60": ("15.00", "30.00"),
        "80.00": ("20.00", "40.00"),
        "80": ("20.00", "40.00"),
        "100.00": ("25.00", "50.00"),
        "100": ("25.00", "50.00"),
        "200.00": ("50.00", "100.00"),
        "200": ("50.00", "100.00"),
        "400.00": ("100.00", "200.00"),
        "400": ("100.00", "200.00"),
        "500.00": ("125.00", "250.00"),
        "500": ("125.00", "250.00"),
        "800.00": ("200.00", "400.00"),
        "800": ("200.00", "400.00"),
    }
    NLim_Blinds_20bb = {
        "0.80": ("0.01", "0.02"),
        "1.60": ("0.02", "0.04"),
        "4": ("0.05", "0.10"),
        "10": ("0.10", "0.25"),
        "20": ("0.25", "0.50"),
        "40": ("0.50", "1.00"),
        "240": ("3.00", "6.00"),
    }

    months = {
        "January": 1,
        "Jan": 1,
        "February": 2,
        "Feb": 2,
        "March": 3,
        "Mar": 3,
        "April": 4,
        "Apr": 4,
        "May": 5,
        "June": 6,
        "Jun": 6,
        "July": 7,
        "Jul": 7,
        "August": 8,
        "Aug": 8,
        "September": 9,
        "Sep": 9,
        "October": 10,
        "Oct": 10,
        "November": 11,
        "Nov": 11,
        "December": 12,
        "Dec": 12,
    }

    sites = {
        "Poker Stars": ("PokerStars", 2),
        "PokerMaster": ("PokerMaster", 25),
        "IPoker": ("iPoker", 14),
        "Party": ("PartyPoker", 9),
        "Pacific": ("PacificPoker", 10),
        "WPN": ("WinningPoker", 24),
        "PokerBros": ("PokerBros", 29),
    }

    # Static regexes
    re_GameInfo = re.compile(
        """
            \*{5}\sHand\sHistory\s(F|f)or\sGame\s(?P<HID>\w+)\s\*{5}(\s\((?P<SITE>Poker\sStars|PokerMaster|Party|PartyPoker|IPoker|Pacific|WPN|PokerBros)\))?\s+
            (.+?\shas\sleft\sthe\stable\.\s+)*
            (.+?\sfinished\sin\s\d+\splace\.\s+)*
            ((?P<CURRENCY>[%(LS)s]))?\s*
            (
             ([%(LS)s]?(?P<SB>[%(NUM)s]+)/[%(LS)s]?(?P<BB>[%(NUM)s]+)\s*(?:%(LEGAL_ISO)s)?\s+(?P<FAST3>fastforward\s)?((?P<LIMIT3>NL|PL|FL|)\s+)?)|
             ((?P<CASHBI>[%(NUM)s]+)\s*(?:%(LEGAL_ISO)s)?\s*)(?P<FAST2>fastforward\s)?(?P<LIMIT2>(NL|PL|FL|))?\s*
            )
            (Tourney\s*)?
            (?P<GAME>(Texas\sHold\'?em|Hold\'?em|Omaha\sHi-Lo|Omaha(\sHi)?|7\sCard\sStud\sHi-Lo|7\sCard\sStud|Double\sHold\'?em|Short\sDeck))\s*
            (Game\sTable\s*)?
            (
             (\((?P<LIMIT>(NL|PL|FL|Limit|))\)\s*)?
             (\((?P<SNG>SNG|STT|MTT)(\sJackPot)?\sTournament\s\#(?P<TOURNO>\d+)\)\s*)?
            )?
            (?:\s\(Buyin\s(?P<BUYIN>[%(LS)s][%(NUM)s]+)\s\+\s(?P<FEE>[%(LS)s][%(NUM)s]+)\))?
            \s*-\s*
            (?P<DATETIME>.+)
            """
        % substitutions,
        re.VERBOSE | re.UNICODE,
    )

    re_HandInfo = re.compile(
        """
            Table\s(?P<TABLE>.+?)?\s+
            ((?: \#|\(|)(?P<TABLENO>\d+)\)?\s+)?
            (\(No\sDP\)\s)?
            \(\s?(?P<PLAY>Real|Play)\s+Money\s?\)\s+(--\s*)? # FIXME: check if play money is correct
            Seat\s+(?P<BUTTON>\d+)\sis\sthe\sbutton
            (\s+Total\s+number\s+of\s+players\s+\:\s+(?P<PLYRS>\d+)/?(?P<MAX>\d+)?)?
            """,
        re.VERBOSE | re.MULTILINE | re.DOTALL,
    )

    re_GameInfoTrny1 = re.compile(
        """
            \*{5}\sHand\sHistory\s(F|f)or\sGame\s(?P<HID>\w+)\s\*{5}\s+
            (?P<LIMIT>(NL|PL|FL|))\s*
            (?P<GAME>(Texas\sHold\'em|Hold\'?em|Omaha\sHi-Lo|Omaha(\sHi)?|7\sCard\sStud\sHi-Lo|7\sCard\sStud|Double\sHold\'em|Short\sDeck))\s+
            (?:(?P<BUYIN>[%(LS)s]?\s?[%(NUM)s]+)\s*(?P<BUYIN_CURRENCY>%(LEGAL_ISO)s)?\s*Buy-in\s+)?
            (\+\s(?P<FEE>[%(LS)s]?\s?[%(NUM)s]+)\sEntry\sFee\s+)?
            Trny:\s?(?P<TOURNO>\d+)\s+
            Level:\s*(?P<LEVEL>\d+)\s+
            ((Blinds|Stakes)(?:-Antes)?)\(
                (?P<SB>[%(NUM)s ]+)\s*
                /(?P<BB>[%(NUM)s ]+)
                (?:\s*-\s*(?P<ANTE>[%(NUM)s ]+)\$?)?
            \)
            \s*\-\s*
            (?P<DATETIME>.+)
            """
        % substitutions,
        re.VERBOSE | re.UNICODE,
    )

    re_GameInfoTrny2 = re.compile(
        """
            \*{5}\sHand\sHistory\s(F|f)or\sGame\s(?P<HID>\w+)\s\*{5}\s+
            (?P<LIMIT>(NL|PL|FL|))\s*
            (?P<GAME>(Texas\sHold\'em|Hold\'?em|Omaha\sHi-Lo|Omaha(\sHi)?|7\sCard\sStud\sHi-Lo|7\sCard\sStud|Double\sHold\'em|Short\sDeck))\s+
            (?:(?P<BUYIN>[%(LS)s]?\s?[%(NUM)s]+)\s*(?P<BUYIN_CURRENCY>%(LEGAL_ISO)s)?\s*Buy-in\s+)?
            (\+\s(?P<FEE>[%(LS)s]?\s?[%(NUM)s]+)\sEntry\sFee\s+)?
            \s*\-\s*
            (?P<DATETIME>.+)
            """
        % substitutions,
        re.VERBOSE | re.UNICODE,
    )

    re_GameInfoTrny3 = re.compile(
        """
            \*{5}\sHand\sHistory\s(F|f)or\sGame\s(?P<HID>\w+)\s\*{5}\s\((?P<SITE>Poker\sStars|PokerMaster|Party|IPoker|Pacific|WPN|PokerBros)\)\s+
            Tourney\sHand\s
            (?P<LIMIT>(NL|PL|FL|))\s*
            (?P<GAME>(Texas\sHold\'em|Hold\'?em|Omaha\sHi-Lo|Omaha(\sHi)?|7\sCard\sStud\sHi-Lo|7\sCard\sStud|Double\sHold\'em|Short\sDeck))\s+
            \s*\-\s*
            (?P<DATETIME>.+)
            """
        % substitutions,
        re.VERBOSE | re.UNICODE,
    )

    re_Blinds = re.compile(
        """
            ^((Blinds|Stakes)(?:-Antes)?)\(
                (?P<SB>[%(NUM)s ]+)\s*
                /(?P<BB>[%(NUM)s ]+)
                (?:\s*-\s*(?P<ANTE>[%(NUM)s ]+)\$?)?
            \)$"""
        % substitutions,
        re.VERBOSE | re.MULTILINE,
    )

    re_TourNoLevel = re.compile(
        """
            Trny:\s?(?P<TOURNO>\d+)\s+
            Level:\s*(?P<LEVEL>\d+)
        """,
        re.VERBOSE,
    )

    re_PlayerInfo = re.compile(
        """
          (S|s)eat\s?(?P<SEAT>\d+):\s
          (?P<PNAME>.*)\s
          \(\s*[%(LS)s]?(?P<CASH>[%(NUM)s]+)\s*(?:%(LEGAL_ISO)s|)\s*\)
          """
        % substitutions,
        re.VERBOSE | re.UNICODE,
    )

    re_NewLevel = re.compile(
        "Blinds(-Antes)?\((?P<SB>[%(NUM)s ]+)/(?P<BB>[%(NUM)s ]+)(?:\s*-\s*(?P<ANTE>[%(NUM)s ]+))?\)" % substitutions,
        re.VERBOSE | re.MULTILINE | re.DOTALL,
    )
    re_CountedSeats = re.compile("Total\s+number\s+of\s+players\s*:\s*(?P<COUNTED_SEATS>\d+)", re.MULTILINE)
    re_Identify = re.compile("\*{5}\sHand\sHistory\s[fF]or\sGame\s\d+\w+?\s")
    re_SplitHands = re.compile("Game\s*\#\d+\s*starts.\n\n+\#Game\s*No\s*\:\s*\d+\s*")
    re_TailSplitHands = re.compile("(\x00+)")
    lineSplitter = "\n"
    re_Button = re.compile("Seat (?P<BUTTON>\d+) is the button", re.MULTILINE)
    re_Board = re.compile(r"\[(?P<CARDS>.+)\]")
    re_NoSmallBlind = re.compile(
        "^There is no Small Blind in this hand as the Big Blind " "of the previous hand left the table", re.MULTILINE
    )
    re_20BBmin = re.compile(r"Table 20BB Min")
    re_Cancelled = re.compile("Table\sClosed\s?", re.MULTILINE)
    re_Disconnected = re.compile("Connection\sLost\sdue\sto\ssome\sreason\s?", re.MULTILINE)
    re_GameStartLine = re.compile("Game\s\#\d+\sstarts", re.MULTILINE)
    re_emailedHand = re.compile(r"\*\*\sSummary\s\*\*")

    re_WinningRankOne = re.compile(
        r"^Congratulations to player (?P<PNAME>.+?) for winning tournament .*",
        re.MULTILINE,
    )

    re_WinningRankOther = re.compile(
        r"^Player\s+(?P<PNAME>.+?)\s+finished\s+in\s+(?P<RANK>\d+)\s+place\s+and\s+received\s+(?P<CURRENCY_SYMBOL>[€$])(?P<AMT>[,\.0-9]+)\s+(?P<CURRENCY_CODE>[A-Z]{3})$",
        re.MULTILINE,
    )

    re_RankOther = re.compile(
        r"^Player\s+(?P<PNAME>.+?)\s+finished\s+in\s+(?P<RANK>\d+)$",
        re.MULTILINE,
    )

    def __init__(
        self,
        config,
        in_path="-",
        out_path="-",
        index=0,
        autostart=True,
        starsArchive=False,
        ftpArchive=False,
        sitename="PartyPoker",
    ):
        log.debug("enter method __init__ of PartyPoker.")
        super().__init__(config, in_path, out_path, index, autostart, starsArchive, ftpArchive, sitename)
        log.debug("init parser PartyPoker.")
        self.last_bet = {}
        self.player_bets = {}

    def allHandsAsList(self):
        log.debug("enter method allHandsAsList.")
        hands = HandHistoryConverter.allHandsAsList(self)
        if hands is None:
            log.debug("no hand found in allHandsAsList.")
            return []
        filtered_hands = list(filter(lambda text: len(text.strip()), hands))
        log.debug(f"{len(filtered_hands)} hand filtered in allHandsAsList.")
        return filtered_hands

    def compilePlayerRegexs(self, hand):
        log.debug("enter method compilePlayerRegexs.")
        players = set([player[1] for player in hand.players])
        log.debug(f"List of players to compile : {players}")
        if not hasattr(self, "compiledPlayers") or not players <= self.compiledPlayers:
            log.debug("Compiling specific regex for players.")
            self.compiledPlayers = players
            player_re = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"
            subst = {
                "PLYR": player_re,
                "CUR_SYM": self.sym.get(hand.gametype["currency"], ""),
                "CUR": hand.gametype["currency"],
                "BRAX": r"\[\(\)\]",
            }
            # define regex
            self.re_PostSB = re.compile(
                rf"{subst['PLYR']} posts small blind [\[\(\)\]]?{subst['CUR_SYM']}?(?P<SB>[.,0-9]+)\s*({subst['CUR']})?[\[\(\)\]]?\.?\s*$",
                re.MULTILINE,
            )
            log.debug("Regex re_PostSB compiled.")
            self.re_PostBB = re.compile(
                rf"{subst['PLYR']} posts big blind [\[\(\)\]]?{subst['CUR_SYM']}?(?P<BB>[.,0-9]+)\s*({subst['CUR']})?[\[\(\)\]]?\.?\s*$",
                re.MULTILINE,
            )
            log.debug("Regex re_PostBB compiled.")
            self.re_PostDead = re.compile(
                rf"{subst['PLYR']} posts big blind \+ dead [\[\(\)\]]?{subst['CUR_SYM']}?(?P<BBNDEAD>[.,0-9]+)\s*{subst['CUR_SYM']}?[\[\(\)\]]?\.?\s*$",
                re.MULTILINE,
            )
            log.debug("Regex re_PostDead compiled.")
            self.re_PostBUB = re.compile(
                rf"{subst['PLYR']} posts button blind  ?[\[\(\)\]]?{subst['CUR_SYM']}?(?P<BUB>[.,0-9]+)\s*({subst['CUR']})?[\[\(\)\]]?\.?\s*$",
                re.MULTILINE,
            )
            log.debug("Regex re_PostBUB compiled.")
            self.re_Antes = re.compile(
                rf"{subst['PLYR']} posts ante(?: of)? [\[\(\)\]]?{subst['CUR_SYM']}?(?P<ANTE>[.,0-9]+)\s*({subst['CUR']})?[\[\(\)\]]?\.?\s*$",
                re.MULTILINE,
            )
            log.debug("Regex re_Antes compiled.")
            self.re_Action = re.compile(
                r"""
                    (?P<PNAME>.+?)\s(?P<ATYPE>bets|checks|raises|completes|bring-ins|calls|folds|is\sall-In|double\sbets)(?:\s*[\[\(\)\]]?\s?(€|$)?(?P<BET>[.,\d]+)\s*(EUR|DOL)?\s*[\]\)]?)?(?:\sto\s[.,\d]+)?\.?\s*$
                """,
                re.MULTILINE | re.VERBOSE,
            )

            log.debug("Regex re_Action compiled.")
            self.re_HeroCards = re.compile(rf"Dealt to {subst['PLYR']} \[\s*(?P<NEWCARDS>.+)\s*\]", re.MULTILINE)
            log.debug("Regex re_HeroCards compiled.")
            self.re_ShownCards = re.compile(
                rf"{subst['PLYR']} (?P<SHOWED>(?:doesn\'t )?shows?) \[ *(?P<CARDS>.+) *\](?P<COMBINATION>.+)\.",
                re.MULTILINE,
            )
            log.debug("Regex re_ShownCards compiled.")
            self.re_CollectPot = re.compile(
                rf"{subst['PLYR']}\s+wins\s+(Lo\s\()?{subst['CUR_SYM']}?(?P<POT>[.,\d]+)\s*({subst['CUR']})?\)?",
                re.MULTILINE | re.VERBOSE,
            )
            log.debug("Regex re_CollectPot compiled.")
        else:
            log.debug("regex already compiled.")

    def readSupportedGames(self):
        log.debug("Enter method readSupportedGames.")
        supported_games = [
            ["ring", "hold", "nl"],
            ["ring", "hold", "pl"],
            ["ring", "hold", "fl"],
            ["ring", "stud", "fl"],
            ["tour", "hold", "nl"],
            ["tour", "hold", "pl"],
            ["tour", "hold", "fl"],
            ["tour", "stud", "fl"],
        ]
        log.debug(f"supported games : {supported_games}")
        return supported_games

    def readSTP(self, hand):
        log.debug("Entera method readSTP.")
        log.debug("Method readSTP non implemented.")
        pass

    def determineGameType(self, handText):
        log.debug("Enter method determineGameType.")
        handText = handText.replace("\x00", "")
        info, extra = {}, {}
        m = self.re_GameInfo.search(handText)
        log.debug(f"Search with re_GameInfo : {'Found' if m else 'Not found'}")
        if not m:
            m = self.re_GameInfoTrny1.search(handText)
            log.debug(f"Search with re_GameInfoTrny1 : {'Found' if m else 'Not Found'}")
        if not m:
            m = self.re_GameInfoTrny2.search(handText)
            log.debug(f"Search with re_GameInfoTrny2 : {'Found' if m else 'Not Found'}")
            m2 = self.re_TourNoLevel.search(handText)
            m3 = self.re_Blinds.search(handText)
            if m2 and m3:
                extra.update(m2.groupdict())
                extra.update(m3.groupdict())
                log.debug("More Informations added from re_TourNoLevel and re_Blinds.")
            else:
                m = None
        if not m:
            m = self.re_GameInfoTrny3.search(handText)
            log.debug(f"Search with re_GameInfoTrny3 : {'Found' if m else 'Not Found'}")
        if not m:
            m = self.re_Disconnected.search(handText)
            log.debug(f"Search with re_Disconnected : {'Found' if m else 'Not Found'}")
            if m:
                message = "Player Disconnected"
                log.debug(f"{message}")
                raise FpdbHandPartial(f"Partial hand history: {message}")
            m = self.re_Cancelled.search(handText)
            log.debug(f"Search with re_Cancelled : {'Found' if m else 'Not Found'}")
            if m:
                message = "Table Closed"
                log.debug(f"{message}")
                raise FpdbHandPartial(f"Partial hand history: {message}")
            m = self.re_GameStartLine.match(handText)
            log.debug(f"Search with re_GameStartLine : {'Found' if m else 'Not Found'}")
            if m and len(handText) < 50:
                message = "Game start line"
                log.debug(f"{message}")
                raise FpdbHandPartial(f"Partial hand history: {message}")
            tmp = handText[:200]
            log.error(f"PartyPokerToFpdb.determineGameType: '{tmp}'")
            raise FpdbParseError("Hand type determination failed.")

        mg = m.groupdict()
        mg.update(extra)
        log.debug(f"Informations on the extracted hand : {mg}")

        if "SITE" in mg and mg["SITE"] is not None:
            self.sitename = self.sites.get(mg["SITE"], (self.sitename,))[0]
            self.siteId = self.sites.get(mg["SITE"], (self.siteId,))[1]
            log.info(f"self.siteId: {self.siteId}")
            log.info(f"self.sitename: {self.sitename}")

        if "LIMIT" in mg and mg["LIMIT"] is not None:
            info["limitType"] = self.limits.get(mg["LIMIT"], "fl")
            log.debug(f"limitType defined at : {info['limitType']} from LIMIT")
        if "LIMIT2" in mg and mg["LIMIT2"] is not None:
            info["limitType"] = self.limits.get(mg["LIMIT2"], "fl")
            log.debug(f"limitType defined at : {info['limitType']} from LIMIT2")
        if "LIMIT3" in mg and mg["LIMIT3"] is not None:
            info["limitType"] = self.limits.get(mg["LIMIT3"], "fl")
            log.debug(f"limitType defined atà : {info['limitType']} from LIMIT3")
        if "FAST2" in mg and mg["FAST2"] is not None:
            info["fast"] = True
            log.debug("Mode fast defined at True from FAST2")
        elif "FAST3" in mg and mg["FAST3"] is not None:
            info["fast"] = True
            log.debug("Mode fast defined at True from FAST3")
        else:
            info["fast"] = False
            log.debug("Mode fast defined at False")
        if mg.get("LIMIT") is None and mg.get("LIMIT2") is None and mg.get("LIMIT3") is None:
            info["limitType"] = "fl"
            log.debug("limitType defined at 'fl'")

        if "GAME" in mg and mg["GAME"] is not None:
            info["base"], info["category"] = self.games.get(mg["GAME"], ("hold", "holdem"))
            log.debug(f"base: {info['base']}, category: {info['category']} from GAME")
        else:
            log.error("game not identified.")
            raise FpdbParseError("game not identified.")

        if "CASHBI" in mg and mg["CASHBI"] is not None:
            mg["CASHBI"] = self.clearMoneyString(mg["CASHBI"])
            log.debug(f"CASHBI cleaned : {mg['CASHBI']}")
            m_20BBmin = self.re_20BBmin.search(handText)
            if m_20BBmin:
                try:
                    info["sb"], info["bb"] = self.NLim_Blinds_20bb.get(mg["CASHBI"], ("0.01", "0.02"))
                    info["buyinType"] = "shallow"
                    log.debug(
                        f"sb: {info['sb']}, bb: {info['bb']}, buyinType: {info['buyinType']} from NLim_Blinds_20bb"
                    )
                except KeyError:
                    tmp = handText[:200]
                    log.error(
                        f"PartyPokerToFpdb.determineGameType: NLim_Blinds_20bb has no lookup for '{mg['CASHBI']}' - '{tmp}'"
                    )
                    raise FpdbParseError
            else:
                try:
                    if Decimal(mg["CASHBI"]) >= 10000:
                        nl_bb = str((Decimal(mg["CASHBI"]) / 100).quantize(Decimal("0.01")))
                        info["buyinType"] = "deep"
                        log.debug(f"buyinType defined at 'deep', nl_bb: {nl_bb}")
                    else:
                        nl_bb = str((Decimal(mg["CASHBI"]) / 50).quantize(Decimal("0.01")))
                        info["buyinType"] = "regular"
                        log.debug(f"buyinType defined at 'regular', nl_bb: {nl_bb}")
                    info["sb"], info["bb"] = self.Lim_Blinds.get(nl_bb, ("0.01", "0.02"))
                    log.debug(f"sb: {info['sb']}, bb: {info['bb']} from Lim_Blinds")
                except KeyError:
                    tmp = handText[:200]
                    log.error(
                        f"PartyPokerToFpdb.determineGameType: Lim_Blinds has no lookup for '{mg['CASHBI']}' - '{tmp}'"
                    )
                    raise FpdbParseError
        else:
            if info.get("category") == "6_holdem":
                info["sb"] = "0"
                info["bb"] = self.clearMoneyString(mg.get("SB", "0.02"))
                log.debug(f"sb: {info['sb']}, bb: {info['bb']} for category '6_holdem'")
            else:
                m = self.re_NewLevel.search(handText)
                if m:
                    mg["SB"] = m.group("SB")
                    mg["BB"] = m.group("BB")
                    log.debug(f"sb: {mg['SB']}, bb: {mg['BB']} from re_NewLevel")
                info["sb"] = self.clearMoneyString(mg.get("SB", "0.01"))
                info["bb"] = self.clearMoneyString(mg.get("BB", "0.02"))
                log.debug(f"sb: {info['sb']}, bb: {info['bb']} after cleaning")
            info["buyinType"] = "regular"
            log.debug("buyinType defined at 'regular'")

        if "CURRENCY" in mg:
            info["currency"] = self.currencies.get(mg["CURRENCY"], "EUR")
            log.debug(f"currency define at : {info['currency']} from CURRENCY")
        else:
            info["currency"] = "EUR"
            log.debug("currency defined by defautl at 'EUR'")

        if "MIXED" in mg and mg["MIXED"] is not None:
            info["mix"] = self.mixes.get(mg["MIXED"], "none")
            log.debug(f"mix defined at : {info['mix']} from MIXED")

        if "TOURNO" in mg and mg["TOURNO"] is None:
            info["type"] = "ring"
            log.debug("type defined at 'ring' because TOURNO is None")
        else:
            info["type"] = "tour"
            info["currency"] = "T$"
            log.debug("type defined at 'tour' and currency at 'T$'")

        if info.get("limitType") == "fl" and info.get("bb") is not None:
            if info["type"] == "ring":
                try:
                    info["sb"], info["bb"] = self.Lim_Blinds.get(mg["BB"], ("0.01", "0.02"))
                    log.debug(f"sb: {info['sb']}, bb: {info['bb']} from Lim_Blinds from 'ring'")
                except KeyError:
                    tmp = handText[:200]
                    log.error(
                        f"PartyPokerToFpdb.determineGameType: Lim_Blinds has no lookup for '{mg['BB']}' - '{tmp}'"
                    )
                    raise FpdbParseError
            else:
                info["sb"] = str((Decimal(mg.get("SB", "0")) / 2).quantize(Decimal("0.01")))
                info["bb"] = str(Decimal(mg.get("SB", "0")).quantize(Decimal("0.01")))
                log.debug(f"sb: {info['sb']}, bb: {info['bb']} for 'tour'")

        log.debug(f"Game type defined : {info}")
        return info

    def readHandInfo(self, hand):
        log.debug("Enter method readHandInfo.")
        info, m2, extra, type3 = {}, None, {}, False
        hand.handText = hand.handText.replace("\x00", "")

        if self.re_emailedHand.search(hand.handText):
            hand.emailedHand = True
        else:
            hand.emailedHand = False

        m = self.re_HandInfo.search(hand.handText, re.DOTALL)
        log.debug(f"Search with re_HandInfo : {'Found' if m else 'Not Found'}")

        if hand.gametype["type"] == "ring" or hand.emailedHand:
            m2 = self.re_GameInfo.search(hand.handText)
            log.debug(f"Search with re_GameInfo for 'ring' or 'emailedHand' : {'Found' if m2 else 'Not Found'}")
        else:
            m2 = self.re_GameInfoTrny1.search(hand.handText)
            log.debug(f"Search with re_GameInfoTrny1 for 'tour' : {'Found' if m2 else 'Not Found'}")
            if not m2:
                m2 = self.re_GameInfoTrny2.search(hand.handText)
                log.debug(f"Search with re_GameInfoTrny2 for 'tour' : {'Found' if m2 else 'Not Found'}")
                m3 = self.re_TourNoLevel.search(hand.handText)
                m4 = self.re_Blinds.search(hand.handText)
                if m3 and m4:
                    extra.update(m3.groupdict())
                    extra.update(m4.groupdict())
                    log.debug("Adding info from re_TourNoLevel and re_Blinds.")
                else:
                    m2 = self.re_GameInfoTrny3.search(hand.handText)
                    type3 = True
                    log.debug(f"Search with re_GameInfoTrny3 for 'tour' : {'Found' if m2 else 'Not Found'}")
        if not m:
            m = self.re_Disconnected.search(hand.handText)
            log.debug(f"Search with re_Disconnected : {'Found' if m else 'Not Found'}")
            if m:
                message = "Player Disconnected"
                log.debug(f"{message}")
                raise FpdbHandPartial(f"Partial hand history: {message}")
            m = self.re_Cancelled.search(hand.handText)
            log.debug(f"Search with re_Cancelled : {'Found' if m else 'Not Found'}")
            if m:
                message = "Table Closed"
                log.debug(f"{message}")
                raise FpdbHandPartial(f"Partial hand history: {message}")
            m = self.re_GameStartLine.match(hand.handText)
            log.debug(f"Search with re_GameStartLine : {'Found' if m else 'Not Found'}")
            if m and len(hand.handText) < 50:
                message = "Game start line"
                log.debug(f"{message}")
                raise FpdbHandPartial(f"Partial hand history: {message}")
            tmp = hand.handText[:200]
            log.error(f"PartyPokerToFpdb.readHandInfo: '{tmp}'")
            raise FpdbParseError("missing infos.")

        if m2 is None:
            tmp = hand.handText[:200]
            log.error(f"PartyPokerToFpdb.readHandInfo: '{tmp}'")
            raise FpdbParseError("missing infos.")

        info.update(m.groupdict())
        info.update(m2.groupdict())
        info.update(extra)
        log.debug(f"infos for hand updated : {info}")

        for key in info:
            if key == "DATETIME":
                log.debug("Manage DATETIME.")
                # Exeample : Saturday, July 25, 07:53:52 EDT 2009
                m2 = re.search(
                    r"\w+?,?\s*?(?P<M>\w+)\s+(?P<D>\d+),?\s+(?P<H>\d+):(?P<MIN>\d+):(?P<S>\d+)\s+((?P<TZ>[A-Z]+)\s+)?(?P<Y>\d+)",
                    info[key],
                    re.UNICODE,
                )
                if m2:
                    timezone = m2.group("TZ") if m2.group("TZ") else "ET"
                    month = self.months.get(m2.group("M"))
                    if not month:
                        log.error(f"Month unknown : {m2.group('M')}")
                        raise FpdbParseError(f"Month unknown : {m2.group('M')}")
                    datetimestr = (
                        f"{m2.group('Y')}/{month}/{m2.group('D')} {m2.group('H')}:{m2.group('MIN')}:{m2.group('S')}"
                    )
                    try:
                        hand.startTime = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S")
                        hand.startTime = HandHistoryConverter.changeTimezone(hand.startTime, timezone, "UTC")
                        log.debug(f"StartTime : {hand.startTime}")
                    except Exception as e:
                        log.error(f"Error during parsing of date : {e}")
                        raise FpdbParseError("Error during parsing of date.")
                else:
                    log.error(f"Cannot parse date : {info[key]}")
                    raise FpdbParseError(f"Cannot parse date : {info[key]}")

            if key == "HID":
                log.debug("Manage HID.")
                if str(info[key]) == "1111111111":
                    hand.handid = str(int(time.time() * 1000))
                    hand.roundPenny = True
                    log.debug(f"HandID generate : {hand.handid}")
                else:
                    if re.search("[a-z]", info[key]):
                        hand.handid = info[key][:13]
                        hand.roundPenny = True
                        log.debug(f"HandID defined at : {hand.handid} (roundPenny=True)")
                    else:
                        hand.handid = info[key]
                        log.debug(f"HandID define at : {hand.handid}")
                log.debug(f"HandID : {hand.handid}")

            if key == "TABLE":
                log.debug("Manage TABLE.")
                if "TOURNO" in info and info["TOURNO"] is None:
                    if info.get("TABLENO"):
                        hand.tablename = f"{info[key]} {info['TABLENO']}"
                        log.debug(f"TableName defined at : {hand.tablename} (with TABLENO)")
                    else:
                        hand.tablename = info[key]
                        log.debug(f"TableName defined at : {hand.tablename}")
                else:
                    hand.tablename = info.get("TABLENO", "Unknown")
                    log.debug(f"TableName defined at : {hand.tablename} (without TABLENO)")
                log.debug(f"TableName : {hand.tablename}")

            if key == "BUTTON":
                log.debug("Manage BUTTON.")
                hand.buttonpos = int(info[key])
                log.debug(f"Button Position : {hand.buttonpos}")

            if key == "TOURNO":
                log.debug("Manage champ TOURNO.")
                hand.tourNo = info[key]
                if hand.emailedHand:
                    hand.buyin = 0
                    hand.fee = 0
                    hand.buyinCurrency = "NA"
                log.debug(f"Tourney No : {hand.tourNo}")

            if key == "BUYIN":
                log.debug("Manage BUYIN.")
                if info.get("TABLE") and "Freeroll" in info.get("TABLE"):
                    # Freeroll tourney
                    hand.buyin = 0
                    hand.fee = 0
                    hand.buyinCurrency = "FREE"
                    log.debug("Freeroll tourney : buyin and fee defined at 0, buyinCurrency at 'FREE'.")
                elif info[key] is None:
                    # Freeroll tourney
                    hand.buyin = 0
                    hand.fee = 0
                    hand.buyinCurrency = "NA"
                    log.debug("Freeroll tourney : buyin and fee defined at 0, buyinCurrency at 'NA'.")
                elif hand.tourNo is not None:
                    hand.buyin = 0
                    hand.fee = 0
                    hand.buyinCurrency = "NA"
                    if "$" in info[key]:
                        hand.buyinCurrency = "USD"
                    elif "€" in info[key]:
                        hand.buyinCurrency = "EUR"
                    else:
                        log.error(
                            f"PartyPokerToFpdb.readHandInfo: Failed to detect currency Hand ID: '{hand.handid}' - '{info[key]}'"
                        )
                        raise FpdbParseError
                    info[key] = self.clearMoneyString(info[key].strip("$€"))
                    hand.buyin = int(100 * Decimal(info[key]))
                    log.debug(f"buyin cleaned : {info[key]}, buyin calculated : {hand.buyin} {hand.buyinCurrency}")
                    if "FEE" in info and info["FEE"] is not None:
                        info["FEE"] = self.clearMoneyString(info["FEE"].strip("$€"))
                        hand.fee = int(100 * Decimal(info["FEE"]))
                        log.debug(f"Fee cleaned : {info['FEE']}, fee calculated : {hand.fee}")
                    log.debug(f"Buyin : {hand.buyin} {hand.buyinCurrency}, Fee : {hand.fee}")
                log.debug(f"Buyin final : {hand.buyin} {hand.buyinCurrency}, Fee final : {hand.fee}")

            if key == "LEVEL":
                log.debug("Manage LEVEL.")
                hand.level = info[key]
                log.debug(f"Level : {hand.level}")

            if key == "PLAY" and info["PLAY"] != "Real":
                hand.gametype["currency"] = "play"
                log.debug(f"Currency adjust at : {hand.gametype['currency']} (Play Money)")

            if key == "MAX" and info[key] is not None:
                log.debug("Manage MAX.")
                hand.maxseats = int(info[key])
                log.debug(f"Max Seats : {hand.maxseats}")

            if type3:
                log.debug("manage type3.")
                hand.tourNo = info.get("TABLE", "Unknown")
                hand.buyin = 0
                hand.fee = 0
                hand.buyinCurrency = "NA"
                log.debug(
                    f"Type3 ajusté : Tourney No {hand.tourNo}, Buyin {hand.buyin}, Fee {hand.fee}, Currency {hand.buyinCurrency}"
                )

    def readButton(self, hand):
        log.debug("Enter method readButton.")
        m = self.re_Button.search(hand.handText)
        if m:
            hand.buttonpos = int(m.group("BUTTON"))
            log.debug(f"Button Position found : {hand.buttonpos}")
        else:
            log.info("readButton: Button not found.")
        log.debug("Uot method readButton.")

    def readPlayerStacks(self, hand):
        log.debug("Enter method readPlayerStacks.")
        m = self.re_PlayerInfo.finditer(hand.handText)
        maxKnownStack = Decimal("0")
        zeroStackPlayers = []
        self.playerMap = {}
        log.debug("Init variables for readPlayerStacks.")
        for a in m:
            pname = a.group("PNAME").strip()
            cash = self.clearMoneyString(a.group("CASH"))
            log.debug(f"Joueur found : {pname} with CASH = {cash}")
            if hand.emailedHand:
                subst = {"PLYR": re.escape(a.group("PNAME")), "SPACENAME": r"\s(.+)? "}
                re_PlayerName = re.compile(
                    rf"^{subst['PLYR']}(?P<PNAMEEXTRA>{subst['SPACENAME']})balance\s", re.MULTILINE | re.VERBOSE
                )
                m1 = re_PlayerName.search(hand.handText)
                if m1 and len(m1.group("PNAMEEXTRA")) > 1:
                    pname = a.group("PNAME") + m1.group("PNAMEEXTRA")
                    pname = pname.strip()
                    self.playerMap[a.group("PNAME")] = pname
                    log.debug(f"Joueur emailed with name : {pname}")

            if Decimal(cash) > 0:
                # Record the maximum known stack for players with an unknown stack
                maxKnownStack = max(Decimal(cash), maxKnownStack)
                hand.addPlayer(int(a.group("SEAT")), pname, cash)
                log.debug(f"Add player : {pname} at seat {a.group('SEAT')} with €{cash}")
            else:
                # Players with zero stack to be added later
                zeroStackPlayers.append([int(a.group("SEAT")), pname, cash])
                log.debug(f"Player with zero stack detected : {pname} at seat {a.group('SEAT')}")

        if hand.gametype["type"] == "ring":
            log.debug("Treatment of players for a 'ring'.")

            def findFirstEmptySeat(startSeat):
                log.debug(f"Search for the first empty seat from {startSeat}.")
                i = startSeat
                while i in [player[0] for player in hand.players]:
                    i += 1
                    if i > hand.maxseats:
                        i = 1
                    if i > 10:
                        break
                log.debug(f"Seat empty found : {i}")
                return i

            # re_HoleCards = re.compile(r"\*{2} Dealing down cards \*{2}")
            re_JoiningPlayers = re.compile(r"(?P<PLAYERNAME>.+?) has joined the table")
            re_BBPostingPlayers = re.compile(r"(?P<PLAYERNAME>.+?) posts big blind", re.MULTILINE)
            re_LeavingPlayers = re.compile(r"(?P<PLAYERNAME>.+?) has left the table")
            # re_PreDeal = re_HoleCards.split(hand.handText)[0]

            match_JoiningPlayers = re_JoiningPlayers.findall(hand.handText)
            match_LeavingPlayers = re_LeavingPlayers.findall(hand.handText)
            match_BBPostingPlayers = re_BBPostingPlayers.findall(hand.handText)

            log.debug(f"Players joining the table : {match_JoiningPlayers}")
            log.debug(f"Players leaving the table : {match_LeavingPlayers}")
            log.debug(f"Players posting the big blind : {match_BBPostingPlayers}")

            # Add each player with zero stack
            for p in zeroStackPlayers:
                if p[1] in match_JoiningPlayers:
                    p[2] = str(maxKnownStack)
                    log.debug(f"Player {p[1]} joins the table with stack adjusted to €{p[2]}")
                if p[1] not in match_LeavingPlayers:
                    hand.addPlayer(p[0], p[1], p[2])
                    log.debug(f"Addition of player with zero stack : {p[1]} at seat {p[0]} with €{p[2]}")

            seatedPlayers = [player[1] for player in hand.players]
            log.debug(f"Seated players after addition : {seatedPlayers}")

            # Add active players not yet added
            unseatedActivePlayers = list(set(match_BBPostingPlayers) - set(seatedPlayers))
            log.debug(f"Active players not seated : {unseatedActivePlayers}")

            if unseatedActivePlayers:
                for player in unseatedActivePlayers:
                    newPlayerSeat = findFirstEmptySeat(1)
                    hand.addPlayer(newPlayerSeat, player, str(maxKnownStack))
                    log.debug(
                        f"Addition of active player not seated : {player} at seat {newPlayerSeat} with €{maxKnownStack}"
                    )
        log.debug("Method output readPlayerStacks.")

    def markStreets(self, hand):
        log.debug("Enter méthode markStreets.")
        if hand.gametype["base"] in ("hold"):
            log.debug("Base type detection 'hold'.")
            m = re.search(
                r"\*{2} Dealing down cards \*{2}"
                r"(?P<PREFLOP>.+?)"
                r"(?:\*{2} Dealing Flop \*{2} (:?\s*)?(?P<FLOP>\[ \S\S, \S\S, \S\S \].+?))?"
                r"(?:\*{2} Dealing Turn \*{2} (:?\s*)?(?P<TURN>\[ \S\S \].+?))?"
                r"(?:\*{2} Dealing River \*{2} (:?\s*)?(?P<RIVER>\[ \S\S \].+?))?$",
                hand.handText,
                re.DOTALL,
            )
            log.debug(f"Result of streets search for 'hold': {'Found' if m else 'Not Found'}")
        elif hand.gametype["base"] in ("stud"):
            log.debug("Base type detection 'stud'.")
            m = re.search(
                r"(?P<ANTES>.+(?=\*\* Dealing \*\*)|.+)"
                r"(\*\* Dealing \*\*(?P<THIRD>.+(?=\*\* Dealing Fourth street \*\*)|.+))?"
                r"(\*\* Dealing Fourth street \*\*(?P<FOURTH>.+(?=\*\* Dealing Fifth street \*\*)|.+))?"
                r"(\*\* Dealing Fifth street \*\*(?P<FIFTH>.+(?=\*\* Dealing Sixth street \*\*)|.+))?"
                r"(\*\* Dealing Sixth street \*\*(?P<SIXTH>.+(?=\*\* Dealing River \*\*)|.+))?"
                r"(\*\* Dealing River \*\*(?P<SEVENTH>.+))?",
                hand.handText,
                re.DOTALL,
            )
            log.debug(f"Result of streets search for 'stud': {'Found' if m else 'Not Found'}")
        else:
            m = None
            log.warning(f"Streets not supported for the game type : {hand.gametype['base']}")

        if m:
            hand.addStreets(m)
            log.debug(f"Marked sections of the hand : {m.groupdict()}")

            for street in ["PREFLOP", "FLOP", "TURN", "RIVER"]:
                actions = m.group(street) if m.group(street) else "Aucune"
                log.debug(f"Actions for {street} : {actions}")
        else:
            log.error(f"Impossible to mark streets by hand {hand.handid}")
        log.debug("Method output markStreets.")

    def readCommunityCards(self, hand, street):
        log.debug(f"Enter method readCommunityCards for street {street}.")

        if street in ("FLOP", "TURN", "RIVER"):
            log.debug(f"Processing community street cards {street}.")
            m = self.re_Board.search(hand.streets[street])

            if m:
                cards_str = m.group("CARDS")
                log.debug(f"Chain of cards found for {street} : '{cards_str}'")
                cards = self.renderCards(cards_str)
                log.debug(f"Cards returned for {street} : {cards}")
                hand.setCommunityCards(street, cards)
                log.debug(f"Community cards defined for {street}.")
            else:
                log.warning(f"No community maps found for the street {street}.")
        else:
            log.warning(f"readCommunityCards: Unknown or unsupported street '{street}'.")

        log.debug("Method output readCommunityCards.")

    def readAntes(self, hand):
        log.debug("Enter method readAntes.")
        for m in self.re_Antes.finditer(hand.handText):
            ante = self.clearMoneyString(m.group("ANTE"))
            hand.addAnte(m.group("PNAME"), ante)
            log.debug(f"{m.group('PNAME')} posts ante €{ante}")
        log.debug("Method output readAntes.")

    def readBlinds(self, hand):
        noSmallBlind = bool(self.re_NoSmallBlind.search(hand.handText))
        if (
            hand.gametype["type"] == "ring"
            or hand.gametype["sb"] is None
            or hand.gametype["bb"] is None
            or hand.roundPenny
        ):
            try:
                assert noSmallBlind == False
                for m in self.re_PostSB.finditer(hand.handText):
                    hand.addBlind(m.group("PNAME"), "small blind", self.clearMoneyString(m.group("SB")))
                    if hand.gametype["sb"] is None:
                        hand.gametype["sb"] = self.clearMoneyString(m.group("SB"))
            except:  # no small blind
                hand.addBlind(None, None, None)

            for a in self.re_PostBB.finditer(hand.handText):
                hand.addBlind(a.group("PNAME"), "big blind", self.clearMoneyString(a.group("BB")))
                if hand.gametype["bb"] is None:
                    hand.gametype["bb"] = self.clearMoneyString(a.group("BB"))

            for a in self.re_PostBUB.finditer(hand.handText):
                hand.addBlind(a.group("PNAME"), "button blind", self.clearMoneyString(a.group("BUB")))

            for a in self.re_PostDead.finditer(hand.handText):
                hand.addBlind(a.group("PNAME"), "both", self.clearMoneyString(a.group("BBNDEAD")))
        else:
            # party doesn't track blinds for tournaments
            # so there're some cra^Wcaclulations
            if hand.buttonpos == 0:
                self.readButton(hand)
            # NOTE: code below depends on Hand's implementation
            # playersMap - dict {seat: (pname,stack)}
            playersMap = dict([(f[0], f[1:3]) for f in hand.players if f[1] in hand.handText.split("Trny:")[-1]])
            maxSeat = max(playersMap)

            def findFirstNonEmptySeat(startSeat):
                while startSeat not in playersMap:
                    if startSeat >= maxSeat:
                        startSeat = 0
                    startSeat += 1
                return startSeat

            smartMin = lambda A, B: A if float(A) <= float(B) else B

            if noSmallBlind:
                hand.addBlind(None, None, None)
                smallBlindSeat = int(hand.buttonpos)
            else:
                if len(hand.players) == 2:
                    smallBlindSeat = int(hand.buttonpos)
                else:
                    smallBlindSeat = findFirstNonEmptySeat(int(hand.buttonpos) + 1)
                blind = smartMin(hand.sb, playersMap[smallBlindSeat][1])
                hand.addBlind(playersMap[smallBlindSeat][0], "small blind", blind)

            if hand.gametype["category"] == "6_holdem":
                bigBlindSeat = findFirstNonEmptySeat(smallBlindSeat + 1)
                blind = smartMin(hand.bb, playersMap[bigBlindSeat][1])
                hand.addBlind(playersMap[bigBlindSeat][0], "button blind", blind)
            else:
                bigBlindSeat = findFirstNonEmptySeat(smallBlindSeat + 1)
                blind = smartMin(hand.bb, playersMap[bigBlindSeat][1])
                hand.addBlind(playersMap[bigBlindSeat][0], "big blind", blind)

    def readBringIn(self, hand):
        log.debug("Enter method readBringIn.")
        log.debug("Method readBringIn not implemented.")
        pass

    def readHoleCards(self, hand):
        log.debug("Enter method readHoleCards.")
        # Read hero's cards
        for street in ("PREFLOP",):
            if street in hand.streets:
                log.debug(f"Read holeCards for street {street}.")
                for found in self.re_HeroCards.finditer(hand.streets[street]):
                    hand.hero = found.group("PNAME")
                    newcards = self.renderCards(found.group("NEWCARDS"))
                    hand.addHoleCards(street, hand.hero, closed=newcards, shown=False, mucked=False, dealt=True)
                    log.debug(f"holeCards of {hand.hero} : {newcards}")

        # Read other player's cards
        for street, text in hand.streets.items():
            if not text or street in ("PREFLOP", "DEAL"):
                continue
            log.debug(f"Read holeCards for street {street}.")
            for found in self.re_HeroCards.finditer(text):
                player = found.group("PNAME")
                newcards = self.renderCards(found.group("NEWCARDS"))
                hand.addHoleCards(street, player, open=newcards, closed=[], shown=False, mucked=False, dealt=False)
                log.debug(f"holeCards of {player} at {street} : {newcards}")
        log.debug("Method output readHoleCards.")

    def readAction(self, hand, street):
        m = self.re_Action.finditer(hand.streets[street])
        for action in m:
            acts = action.groupdict()
            # print "DEBUG: acts: %s %s" % (street, acts)
            playerName = action.group("PNAME")
            if ":" in playerName:
                continue  # captures chat
            if self.playerMap.get(playerName):
                playerName = self.playerMap.get(playerName)
            amount = self.clearMoneyString(action.group("BET")) if action.group("BET") else None
            actionType = action.group("ATYPE")

            if actionType == "folds":
                hand.addFold(street, playerName)
            elif actionType == "checks":
                hand.addCheck(street, playerName)
            elif actionType == "calls":
                hand.addCall(street, playerName, amount)
            elif actionType == "raises":
                if street == "PREFLOP" and playerName in [
                    item[0] for item in hand.actions["BLINDSANTES"] if item[2] != "ante"
                ]:
                    # preflop raise from blind
                    hand.addCallandRaise(street, playerName, amount)
                else:
                    hand.addCallandRaise(street, playerName, amount)
            elif actionType == "bets" or actionType == "double bets":
                hand.addBet(street, playerName, amount)
            elif actionType == "completes":
                hand.addComplete(street, playerName, amount)
            elif actionType == "bring-ins":
                hand.addBringIn(playerName, amount)
            elif actionType == "is all-In":
                if amount:
                    hand.addAllIn(street, playerName, amount)
            else:
                log.error(
                    (("PartyPokerToFpdb: Unimplemented %s: '%s' '%s'") + " hid:%s")
                    % ("readAction", playerName, actionType, hand.handid)
                )
                raise FpdbParseError

    def readShowdownActions(self, hand):
        log.debug("Enter readShowdownActions.")

        log.debug("Method readShowdownActions not implemented (managed in readShownCards).")
        pass

    def readCollectPot(self, hand):
        hand.setUncalledBets(True)
        for m in self.re_CollectPot.finditer(hand.handText):
            hand.addCollectPot(player=m.group("PNAME"), pot=self.clearMoneyString(m.group("POT")))

    def readShownCards(self, hand):
        log.debug("Enter method readShownCards.")
        for m in self.re_ShownCards.finditer(hand.handText):
            if m.group("CARDS"):
                cards = self.renderCards(m.group("CARDS"))
                mucked = "SHOWED" in m.groupdict() and m.group("SHOWED") != "shows"
                hand.addShownCards(
                    cards=cards, player=m.group("PNAME"), shown=True, mucked=mucked, string=m.group("COMBINATION")
                )
                log.debug(f"{m.group('PNAME')} showed cards : {cards}")
        log.debug("Method output readShownCards.")

    def readSummaryInfo(self, summaryInfoList):
        log.info("Enter method readSummaryInfo.")

        log.debug("Method readSummaryInfo not implémented.")
        return True

    def convert_to_decimal(self, string):
        dec = self.clearMoneyString(string)
        dec = Decimal(dec)
        return dec

    def readTourneyResults(self, hand):
        """Reads tournament results and adds winnings or ranks to the relevant data structures."""
        log.debug("Enter Method readTourneyResults.")

        # Initialize data structures to store results
        log.debug("Initializing data structures for tournament results.")
        hand.winnings = {}  # Initialisation des gains
        hand.ranks = {}  # Initialisation des rangs
        koAmounts = {}
        winner = None
        hand.isProgressive = False  # Default to non-progressive KO
        log.debug("Set hand.isProgressive to False (non-progressive KO).")

        # Process the tournament winner (rank 1)
        log.debug("Processing the tournament winner (rank 1).")
        m = self.re_WinningRankOne.search(hand.handText)
        if m:
            log.debug("Regex re_WinningRankOne matched.")
            winner = m.group("PNAME")
            log.debug(f"Winner found: {winner}")

            # Assuming a winning amount in `re_WinningRankOne` pattern as `AMT`
            if "AMT" in m.groupdict():
                amt_str = m.group("AMT").replace(",", "")
                try:
                    amount = Decimal(amt_str)
                    log.debug(f"Winning amount for {winner}: {amount}")
                except Exception as e:
                    log.error(f"Error converting winning amount '{amt_str}' to Decimal: {e}")
                    amount = Decimal(0)
                hand.winnings[winner] = amount
                log.debug(f"Set hand.winnings[{winner}] = {amount}")
            else:
                hand.winnings[winner] = Decimal(0)  # Default amount if none specified
                log.debug(f"No winning amount specified for {winner}. Set hand.winnings[{winner}] = 0")

            hand.ranks[winner] = 1  # Store the rank for the winner
            log.debug(f"Set hand.ranks[{winner}] = 1")
        else:
            log.debug("Regex re_WinningRankOne did not match. No winner found.")

        # Process other ranked players who received winnings
        log.debug("Processing other ranked players who received winnings.")
        for match in self.re_WinningRankOther.finditer(hand.handText):
            log.debug("Found a match with re_WinningRankOther.")
            pname = match.group("PNAME")
            rank = int(match.group("RANK"))
            amt_str = match.group("AMT").replace(",", "")
            try:
                amount = Decimal(amt_str)
                log.debug(f"Player {pname} has rank {rank} with winnings {amount}")
            except Exception as e:
                log.error(f"Error converting amount '{amt_str}' for player '{pname}' to Decimal: {e}")
                amount = Decimal(0)

            currency_symbol = match.group("CURRENCY_SYMBOL")
            currency_code = match.group("CURRENCY_CODE")
            log.debug(
                f"Player: {pname}, Rank: {rank}, Amount: {amount}, Currency Symbol: {currency_symbol}, Currency Code: {currency_code}"
            )

            # Store rank and winnings in the hand object
            hand.ranks[pname] = rank
            log.debug(f"Set hand.ranks[{pname}] = {rank}")
            hand.winnings[pname] = amount
            log.debug(f"Set hand.winnings[{pname}] = {amount}")

        # Process other ranked players without winnings
        log.debug("Processing other ranked players without winnings.")
        for match in self.re_RankOther.finditer(hand.handText):
            log.debug("Found a match with re_RankOther.")
            pname = match.group("PNAME")
            rank = int(match.group("RANK"))
            log.debug(f"Player {pname} has rank {rank} without winnings.")

            # Store rank only in the hand object for these players
            hand.ranks[pname] = rank
            log.debug(f"Set hand.ranks[{pname}] = {rank}")

        # Skip KO and progressive KO processing for now
        log.debug("Skipping KO and progressive KO processing for now.")
        # Placeholder for future KO/progressive KO handling
        pass

        log.debug("Method readTourneyResults completed.")

        # Optionally, log the final winnings and ranks dictionaries
        log.debug(f"Final hand.winnings: {hand.winnings}")
        log.debug(f"Final hand.ranks: {hand.ranks}")

    @staticmethod
    def getTableTitleRe(type, table_name=None, tournament=None, table_number=None):
        """Returns a regex for searching window titles."""
        log.info(
            f"Enter method getTableTitleRe: type='{type}', table_name='{table_name}', tournament='{tournament}', table_number='{table_number}'"
        )
        regex = rf"{re.escape(table_name)}" if table_name else ""
        if type == "tour":
            if table_name:
                TableName = table_name.split(" ")
                if len(TableName) > 1 and len(TableName[1]) > 6:
                    regex = rf"#?{re.escape(table_number)}"
                else:
                    regex = rf"{re.escape(TableName[0])}.+Table\s#?{re.escape(table_number)}"
            else:
                # sng
                regex = rf"{re.escape(tournament)}.*{re.escape(table_number)}"
        log.info(f"Party.getTableTitleRe: return: '{regex}'")
        log.debug("Method output getTableTitleRe.")
        return regex

    @staticmethod
    def renderCards(string):
        log.debug(f"Enter method renderCards with string: '{string}'")
        cards = string.strip().split(" ")
        rendered_cards = list(filter(len, map(lambda x: x.strip(" ,"), cards)))
        log.debug(f"rendered Cards : {rendered_cards}")
        log.debug("Method output renderCards.")
        return rendered_cards
