#!/usr/bin/env python
#
#    Copyright 2008-2012, Chaz Littlejohn
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


import datetime
import re
from decimal import Decimal

from past.utils import old_div

import MergeStructures
from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger

# import L10n
# _ = L10n.get_translation()

# TODO: straighten out discards for draw games


# PokerTracker HH Format
log = get_logger("parser")


class PokerTracker(HandHistoryConverter):
    # Class Variables
    Structures = None
    sitename = "iPoker"  # Default to iPoker, will be overridden by site detection
    filetype = "text"
    codepage = ("utf8", "cp1252")
    site_id = 14  # Default to iPoker, will be overridden by site detection
    sym = {
        "USD": r"\$",
        "CAD": r"\$",
        "T$": "",
        "EUR": "€",
        "GBP": r"\£",
        "play": "",
    }  # ADD Euro, Sterling, etc HERE
    substitutions = {
        "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP",  # legal ISO currency codes
        "LS": r"\$|€|\£|",  # legal currency symbols - Euro(cp1252, utf-8)
        "PLYR": r"(?P<PNAME>.+?)",
        "NUM": r".,\d",
        "CUR": r"(\$|€||\£|)",
        "BRKTS": r"(\(button\) |\(small blind\) |\(big blind\) |\(button\) \(small blind\) |\(button\) \(big blind\) )?",
    }

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

    limits = {
        "NL": "nl",
        "No Limit": "nl",
        "Pot Limit": "pl",
        "PL": "pl",
        "FL": "fl",
        "Limit": "fl",
        "LIMIT": "fl",
    }
    games = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "Texas Hold'em": ("hold", "holdem"),
        "Holdem": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi": ("hold", "omahahi"),
        "Omaha Hi/Lo": ("hold", "omahahilo"),
    }
    sites = {
        "EverestPoker Game #": ("Everest", 16),
        "GAME #": ("iPoker", 14),
        "MERGE_GAME #": ("Merge", 12),
        "Merge Game #": ("Merge", 12),
        "** Game ID ": ("Microgaming", 20),
        "** Hand # ": ("Microgaming", 20),
    }
    currencies = {"€": "EUR", "$": "USD", "": "T$", "£": "GBP"}

    re_Site = re.compile(
        r"(?P<SITE>EverestPoker\sGame\s\#|GAME\s\#|MERGE_GAME\s\#|Merge\sGame\s\#|\*{2}\s(Game\sID|Hand\s\#)\s)\d+",
    )
    # Static regexes
    re_GameInfo1 = re.compile(
        """
          (?P<SITE>GAME\\s\\#|MERGE_GAME\\s\\#|Merge\\sGame\\s\\#)(?P<HID>[0-9\\-]+)(\\sVersion:[\\d\\.]+\\s(?P<UNCALLED>Uncalled:Y))?(:?\\s+|\\s\\|\\s)
          (?P<GAME>Holdem|Texas\\sHold\'em|Omaha|Omaha\\sHi|Omaha\\sHi/Lo)\\s\\s?
          ((?P<LIMIT>PL|NL|FL|No\\sLimit|Limit|LIMIT|Pot\\sLimit)\\s\\s?)?
          (?P<TOUR>Tournament)?
          (\\(?                            # open paren of the stakes
          (?P<CURRENCY>{LS}|)?
          (?P<SB>[{NUM}]+)/({LS})?
          (?P<BB>[{NUM}]+)
          (?P<BLAH>\\s-\\s[{LS}\\d\\.]+\\sCap\\s-\\s)?        # Optional Cap part
          \\s?(?P<ISO>{LEGAL_ISO})?
          \\)?
          )?(\\s|\\s\\|\\s)                        # close paren of the stakes
          (?P<DATETIME>.*$)
        """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_GameInfo2 = re.compile(
        """
          EverestPoker\\sGame\\s\\#(?P<HID>[0-9]+):\\s+
          (?P<TOUR>Tourney\\sID:\\s(?P<TOURNO>\\d+),\\s)?
          Table\\s(?P<TABLE>.+)?
          \\s-\\s
          ((?P<CURRENCY>{LS}|)?
          (?P<SB>[{NUM}]+)/({LS})?
          (?P<BB>[{NUM}]+))?
          \\s-\\s
          (?P<LIMIT>No\\sLimit|Limit|Pot\\sLimit)\\s
          (?P<GAME>Hold\'em|Omaha|Omaha\\sHi|Omaha\\sHi/Lo)\\s
          (-\\s)?
          (?P<DATETIME>.*$)
        """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_GameInfo3 = re.compile(
        """
          (?P<HID>[0-9]+)(\\sVersion:\\d)?\\sstarting\\s\\-\\s(?P<DATETIME>.*$)\\s
          \\*\\*(?P<TOUR>.+(?P<SPEED>(Turbo|Hyper))?\\((?P<TOURNO>\\d+)\\):Table)?\\s(?P<TABLE>.+)\\s
          \\[((Multi|Single)\\sTable\\s)?(?P<GAME>Hold\'em|Omaha|Omaha\\sHi|Omaha\\sHi/Lo)\\]\\s
          \\((?P<SB>[{NUM}]+)\\|(?P<BB>[{NUM}]+)\\s(?P<LIMIT>NL|FL|PL)\\s\\-\\s(MTT|SNG|STT|(?P<CURRENCY>{LS}|)\\s?Cash\\sGame)(\\sseats:(?P<MAX>\\d+))?.*\\)\\s
          (?P<PLAY>Real|Play)\\sMoney
        """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_PlayerInfo1 = re.compile(
        r"""
          ^Seat\s(?P<SEAT>[0-9]+):\s
          (?P<PNAME>.*)\s
          \((?P<CURRENCY>{LS})?(?P<CASH>[{NUM}]+)(\sin\schips)?\)
          (?P<BUTTON>\sDEALER)?""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_PlayerInfo2 = re.compile(
        r"""
          ^(\-\s)?(?P<PNAME>.*)\s
          sitting\sin\sseat\s(?P<SEAT>[0-9]+)\swith\s
          ({LS})?(?P<CASH>[{NUM}]+)
          (?P<BUTTON>\s?\[Dealer\])?""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_HandInfo_Tour = re.compile(
        r"""
          ^Table\s(?P<TABLE>.*),\s(?P<TOURNO>\d+)(,\s\d+)?\s
          (?P<TOUR>\(Tournament:\s(.+)?\sBuy\-In:\s(?P<BUYIN>(?P<BIAMT>[{LS}\d\.]+)\s?\+?\s?(?P<BIRAKE>[{LS}\d\.]+))\))
          """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_HandInfo_Cash = re.compile(
        r"""
          ^Table\s(?P<TABLE>[^,]+?)(,\sSeats\s(?P<MAX>\d+))?$""".format(),
        re.MULTILINE | re.VERBOSE,
    )

    re_identify = re.compile(
        r"(EverestPoker\sGame\s\#|GAME\s\#|MERGE_GAME\s\#|Merge\sGame\s\#|\*{2}\s(Game\sID|Hand\s\#)\s)\d+",
    )
    re_SplitHands = re.compile("\n\n\n+?")
    re_TailSplitHands = re.compile("(\n\n\n+)")
    re_Button = re.compile(r"The button is in seat #(?P<BUTTON>\d+)", re.MULTILINE)
    re_Board1 = re.compile(r"\[(?P<CARDS>.+)\]")
    re_Board2 = re.compile(r":\s(?P<CARDS>.+)\n")
    re_DateTime1 = re.compile(
        r"""(?P<Y>[0-9]{4})\-(?P<M>[0-9]{2})\-(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""",
        re.MULTILINE,
    )
    re_DateTime2 = re.compile(
        r"""(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})\/(?P<Y>[0-9]{4})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""",
        re.MULTILINE,
    )
    re_DateTime3 = re.compile(
        r"""(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)[\- ]+(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})""",
        re.MULTILINE,
    )
    # revised re including timezone (not currently used):
    # re_DateTime     = re.compile("""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+) \(?(?P<TZ>[A-Z0-9]+)""", re.MULTILINE)

    # These used to be compiled per player, but regression tests say
    # we don't have to, and it makes life faster.
    re_PostSB = re.compile(
        r"^{PLYR}:? ((posts|posted) the small blind( of)?|(Post )?SB) (\- )?{CUR}(?P<SB>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_PostBB = re.compile(
        r"^{PLYR}:? ((posts|posted) the big blind( of)?|posts the dead blind of|(Post )?BB) (\- )?{CUR}(?P<BB>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_Antes = re.compile(
        r"^{PLYR}:? ((posts|posted) (the )?ante( of)?|(Post )?Ante) (\- )?{CUR}(?P<ANTE>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_PostBoth1 = re.compile(
        r"^{PLYR}:? (posts|Post|(Post )?DB) {CUR}(?P<SBBB>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_PostBoth2 = re.compile(
        r"^{PLYR}:? posted to play \- {CUR}(?P<SBBB>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_HeroCards1 = re.compile(
        r"^Dealt to {PLYR}(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(**substitutions),
        re.MULTILINE,
    )
    re_HeroCards2 = re.compile(
        r"rd(s)? to {PLYR}: (?P<OLDCARDS>NONE)?(?P<NEWCARDS>.+)\n".format(**substitutions),
        re.MULTILINE,
    )
    re_Action1 = re.compile(
        r"""^{PLYR}:?(?P<ATYPE>\sbets|\schecks|\sraises|\scalls|\sfolds|\sBet|\sCheck|\sRaise(\sto)?|\sCall|\sFold|\sAllin)(?P<RAISETO>\s\(NF\))?(\sto)?(\s{CUR}(?P<BET>[{NUM}]+))?\s*(and\sis\sall.in)?(and\shas\sreached\sthe\s\[{CUR}\d\.,]+\scap)?(\son|\scards?)?(\s\[(?P<CARDS>.+?)\])?\s*$""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    re_Action2 = re.compile(
        r"""
                        ^{PLYR}(?P<ATYPE>\sbet|\schecked|\sraised(\sto)?|\scalled|\sfolded|\swent\sall\-in)
                        (\s(\-\s)?{CUR}(?P<BET>[{NUM}]+))?\s*$""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    re_ShownCards1 = re.compile(
        r"^{PLYR}:? (?P<SHOWED>shows|Shows|mucked) \[(?P<CARDS>.*)\]".format(**substitutions),
        re.MULTILINE,
    )
    re_ShownCards2 = re.compile(
        "^{PLYR} (?P<SHOWED>shows|mucks): (?P<CARDS>.+)\n".format(**substitutions),
        re.MULTILINE,
    )
    re_CollectPot1 = re.compile(
        r"^{PLYR}:? (collects|wins) {CUR}(?P<POT>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_CollectPot2 = re.compile(
        r"^{PLYR} wins {CUR}(?P<POT>[{NUM}]+)".format(**substitutions), re.MULTILINE,
    )
    re_Cancelled = re.compile(r"Hand\scancelled", re.MULTILINE)
    re_Tournament = re.compile(r"\(Tournament:")
    re_Hole = re.compile(r"\*\*\sDealing\scard")
    re_Currency = re.compile(
        r"\s\-\s(?P<CURRENCY>{CUR})[{NUM}]+\s(Max|Min)".format(**substitutions),
    )
    re_Max = re.compile(r"(\s(?P<MAX>(HU|\d+\sSeat))\s)")
    re_FastFold = re.compile(r"^{PLYR}\sQuick\sFolded".format(**substitutions), re.MULTILINE)

    def compilePlayerRegexs(self, hand) -> None:
        pass

    def detectiPokerSkin(self, handText):
        """Detect specific iPoker skin from hand text content."""
        # Extract table name from hand text
        table_pattern = r"Table\s+(.+?),"
        table_match = re.search(table_pattern, handText)
        table_name = table_match.group(1) if table_match else ""
        
        log.debug(f"Detected table name: {table_name}")
        
        # Map of indicators to skin names (must match Sites table)
        skin_mapping = {
            "redbet": "Redbet Poker",
            "pmu": "PMU Poker", 
            "fdj": "FDJ Poker",
            "betclic": "Betclic Poker",
            "netbet": "NetBet Poker",
            "poker770": "Poker770",
            "barriere": "Barrière Poker",
            "titan": "Titan Poker",
            "bet365": "Bet365 Poker",
            "william hill": "William Hill Poker",
            "williamhill": "William Hill Poker",
            "paddy power": "Paddy Power Poker", 
            "paddypower": "Paddy Power Poker",
            "betfair": "Betfair Poker",
            "coral": "Coral Poker",
            "genting": "Genting Poker",
            "mansion": "Mansion Poker",
            "winner": "Winner Poker",
            "ladbrokes": "Ladbrokes Poker",
            "sky": "Sky Poker",
            "sisal": "Sisal Poker",
            "lottomatica": "Lottomatica Poker",
            "eurobet": "Eurobet Poker",
            "snai": "Snai Poker",
            "goldbet": "Goldbet Poker",
            "casino barcelona": "Casino Barcelona Poker",
            "sportium": "Sportium Poker",
            "marca": "Marca Apuestas Poker",
            "everest": "Everest Poker",
            "bet-at-home": "Bet-at-home Poker",
            "mybet": "Mybet Poker",
            "betsson": "Betsson Poker",
            "betsafe": "Betsafe Poker",
            "nordicbet": "NordicBet Poker",
            "unibet": "Unibet Poker",
            "maria": "Maria Casino Poker",
            "leovegas": "LeoVegas Poker", 
            "mr green": "Mr Green Poker",
            "expekt": "Expekt Poker",
            "coolbet": "Coolbet Poker",
            "chilipoker": "Chilipoker",
            "dafa": "Dafa Poker",
            "dafabet": "Dafabet Poker",
            "fun88": "Fun88 Poker",
            "betfred": "Betfred Poker",
            "guts": "Guts Poker",
            "sportingbet": "Sportingbet Poker",
            "multipoker": "MultiPoker",
            "red star": "Red Star Poker",
            "redstar": "Red Star Poker",
        }
        
        # Check table name and hand text for skin indicators
        search_text = (table_name + " " + handText).lower()
        
        # Specific patterns for French sites
        if any(indicator in search_text for indicator in ["saratov", "scone", "moscow"]):
            # These table name patterns are typical of FDJ Poker
            log.debug("Detected FDJ Poker based on table name pattern")
            return "FDJ Poker"
        
        # Check each mapping
        for indicator, skin_name in skin_mapping.items():
            if indicator in search_text:
                log.debug(f"Detected iPoker skin: {skin_name} from indicator: {indicator}")
                return skin_name
        
        # Default to generic iPoker if no specific skin detected
        log.debug("No specific iPoker skin detected, using default 'iPoker'")
        return "iPoker"

    def is_ipoker_skin(self):
        """Check if current sitename is an iPoker skin."""
        ipoker_skins = {
            "iPoker", "FDJ Poker", "Redbet Poker", "PMU Poker", "Betclic Poker", 
            "NetBet Poker", "Poker770", "Barrière Poker", "Titan Poker", 
            "Bet365 Poker", "William Hill Poker", "Paddy Power Poker", 
            "Betfair Poker", "Coral Poker", "Genting Poker", "Mansion Poker", 
            "Winner Poker", "Ladbrokes Poker", "Sky Poker", "Sisal Poker", 
            "Lottomatica Poker", "Eurobet Poker", "Snai Poker", "Goldbet Poker", 
            "Casino Barcelona Poker", "Sportium Poker", "Marca Apuestas Poker", 
            "Everest Poker", "Bet-at-home Poker", "Mybet Poker", "Betsson Poker", 
            "Betsafe Poker", "NordicBet Poker", "Unibet Poker", "Maria Casino Poker", 
            "LeoVegas Poker", "Mr Green Poker", "Expekt Poker", "Coolbet Poker", 
            "Chilipoker", "Dafa Poker", "Dafabet Poker", "Fun88 Poker", 
            "Betfred Poker", "Guts Poker", "Sportingbet Poker", "MultiPoker", 
            "Red Star Poker"
        }
        return self.sitename in ipoker_skins

    def readSupportedGames(self):
        return [
            ["ring", "hold", "nl"],
            ["ring", "hold", "pl"],
            ["ring", "hold", "fl"],
            ["tour", "hold", "nl"],
            ["tour", "hold", "pl"],
            ["tour", "hold", "fl"],
        ]

    def determineGameType(self, handText):
        m = self.re_Site.search(handText)
        if not m:
            tmp = handText[0:200]
            log.error(f"determine Game Type failed: '{tmp}'")
            raise FpdbParseError

        self.sitename = self.sites[m.group("SITE")][0]
        self.site_id = self.sites[m.group("SITE")][
            1
        ]  # Needs to match id entry in Sites database
        
        # Detect iPoker skin from table name or hand text
        if self.sitename == "iPoker":
            detected_skin = self.detectiPokerSkin(handText)
            if detected_skin != "iPoker":
                self.sitename = detected_skin
                log.debug(f"Detected iPoker skin: {self.sitename}")

        info = {}
        if self.is_ipoker_skin() or self.sitename == "Merge":
            m = self.re_GameInfo1.search(handText)
        elif self.sitename == "Everest":
            m = self.re_GameInfo2.search(handText)
        elif self.sitename == "Microgaming":
            m = self.re_GameInfo3.search(handText)
        if not m:
            tmp = handText[0:200]
            log.error(f"determine Game Type failed: '{tmp}'")
            raise FpdbParseError

        mg = m.groupdict()
        # print 'DEBUG determineGameType', '%r' % mg
        if "LIMIT" in mg and mg["LIMIT"] is not None:
            info["limitType"] = self.limits[mg["LIMIT"]]
        if "GAME" in mg:
            (info["base"], info["category"]) = self.games[mg["GAME"]]
            if mg["LIMIT"] is None:
                if info["category"] == "omahahi":
                    info["limitType"] = "pl"
                elif info["category"] == "holdem":
                    info["limitType"] = "nl"
        if "SB" in mg:
            info["sb"] = self.clearMoneyString(mg["SB"])
        if "BB" in mg:
            info["bb"] = self.clearMoneyString(mg["BB"])
        if "CURRENCY" in mg and mg["CURRENCY"] is not None:
            if self.sitename == "Microgaming" and not mg["CURRENCY"]:
                m1 = self.re_Currency.search(mg["TABLE"])
                if m1:
                    mg["CURRENCY"] = m1.group("CURRENCY")
            if self.is_ipoker_skin() and not mg["CURRENCY"]:
                m1 = self.re_PlayerInfo1.search(handText)
                if m1:
                    mg["CURRENCY"] = m1.group("CURRENCY")
            info["currency"] = self.currencies[mg["CURRENCY"]]
        if "MIXED" in mg and mg["MIXED"] is not None:
            info["mix"] = self.mixes[mg["MIXED"]]

        if "TOUR" in mg and mg["TOUR"] is not None:
            info["type"] = "tour"
            info["currency"] = "T$"
        else:
            info["type"] = "ring"

        if info["limitType"] == "fl" and info["bb"] is not None:
            if info["type"] == "ring":
                try:
                    bb = self.clearMoneyString(mg["BB"])
                    info["sb"] = self.Lim_Blinds[bb][0]
                    info["bb"] = self.Lim_Blinds[bb][1]
                except KeyError:
                    tmp = handText[0:200]
                    log.exception(f"Lim_Blinds has no lookup for '{mg['BB']}' - '{tmp}'")
                    raise FpdbParseError
            else:
                sb = self.clearMoneyString(mg["SB"])
                info["sb"] = str((old_div(Decimal(sb), 2)).quantize(Decimal("0.01")))
                info["bb"] = str(Decimal(sb).quantize(Decimal("0.01")))

        return info

    def readHandInfo(self, hand) -> None:
        info, m = {}, None
        if self.is_ipoker_skin() or self.sitename == "Merge":
            m3 = self.re_Tournament.search(hand.handText, re.DOTALL)
            if m3:
                m = self.re_HandInfo_Tour.search(hand.handText, re.DOTALL)
            else:
                m = self.re_HandInfo_Cash.search(hand.handText, re.DOTALL)
            m2 = self.re_GameInfo1.search(hand.handText)
        elif self.sitename == "Everest":
            m2 = self.re_GameInfo2.search(hand.handText)
        elif self.sitename == "Microgaming":
            m2 = self.re_GameInfo3.search(hand.handText)
        if (
            m is None and self.sitename not in ("Everest", "Microgaming")
        ) or m2 is None:
            tmp = hand.handText[0:200]
            log.error(f"read Hand Info failed: '{tmp}'")
            raise FpdbParseError

        if self.sitename not in ("Everest", "Microgaming"):
            info.update(m.groupdict())
        info.update(m2.groupdict())

        if self.sitename != "Everest" and info.get("UNCALLED") is None:
            hand.setUncalledBets(True)

        # print 'readHandInfo', info
        for key in info:
            if key == "DATETIME":
                # 2008/11/12 10:00:48 CET [2008/11/12 4:00:48 ET] # (both dates are parsed so ET date overrides the other)
                # 2008/08/17 - 01:14:43 (ET)
                # 2008/09/07 06:23:14 ET
                if self.is_ipoker_skin() or self.sitename == "Microgaming":
                    m1 = self.re_DateTime1.finditer(info[key])
                elif self.sitename == "Merge":
                    m1 = self.re_DateTime2.finditer(info[key])
                elif self.sitename == "Everest":
                    m1 = self.re_DateTime3.finditer(info[key])
                datetimestr = "2000/01/01 00:00:00"  # default used if time not found
                for a in m1:
                    datetimestr = "{}/{}/{} {}:{}:{}".format(
                        a.group("Y"),
                        a.group("M"),
                        a.group("D"),
                        a.group("H"),
                        a.group("MIN"),
                        a.group("S"),
                    )
                    # tz = a.group('TZ')  # just assume ET??
                    # print "   tz = ", tz, " datetime =", datetimestr
                hand.startTime = datetime.datetime.strptime(
                    datetimestr, "%Y/%m/%d %H:%M:%S",
                )  # also timezone at end, e.g. " ET"
                hand.startTime = HandHistoryConverter.changeTimezone(
                    hand.startTime, "ET", "UTC",
                )
            if key == "HID":
                if self.sitename == "Merge":
                    hand.handid = info[key][:8] + info[key][9:]
                else:
                    hand.handid = info[key]
            if key == "TOURNO":
                hand.tourNo = info[key]
            if key == "BUYIN" and hand.tourNo is not None:
                tourneyname = ""
                if self.sitename == "Merge":
                    if self.Structures is None:
                        self.Structures = MergeStructures.MergeStructures()
                    tourneyname = re.split(",", m.group("TABLE"))[0].strip()
                    structure = self.Structures.lookupSnG(
                        tourneyname, hand.startTime,
                    )
                    if structure is not None:
                        hand.buyin = int(100 * structure["buyIn"])
                        hand.fee = int(100 * structure["fee"])
                        hand.buyinCurrency = structure["currency"]
                        hand.maxseats = structure["seats"]
                        hand.isSng = True
                    else:
                        # print 'DEBUG', 'no match for tourney %s tourNo %s' % (tourneyname, hand.tourNo)
                        hand.buyin = 0
                        hand.fee = 0
                        hand.buyinCurrency = "NA"
                        hand.maxseats = None
                if self.sitename != "Merge" or hand.buyin == 0:
                    if info[key] == "Freeroll" or "Free" in tourneyname:
                        hand.buyin = 0
                        hand.fee = 0
                        hand.buyinCurrency = "FREE"
                    else:
                        if info[key].find("$") != -1:
                            hand.buyinCurrency = "USD"
                        elif info[key].find("£") != -1:
                            hand.buyinCurrency = "GBP"
                        elif info[key].find("€") != -1:
                            hand.buyinCurrency = "EUR"
                        elif re.match("^[0-9+]*$", info[key]):
                            hand.buyinCurrency = "play"
                        else:
                            # FIXME: handle other currencies, play money
                            log.error(
                                f"Failed to detect currency. Hand ID: {hand.handid}: '{info[key]}'",
                            )
                            raise FpdbParseError

                        info["BIAMT"] = info["BIAMT"].strip("$€£")
                        info["BIRAKE"] = info["BIRAKE"].strip("$€£")

                        hand.buyin = int(100 * Decimal(info["BIAMT"]))
                        hand.fee = int(100 * Decimal(info["BIRAKE"]))
            if key == "TABLE":
                if hand.gametype["type"] == "tour":
                    hand.tablename = "0"
                elif hand.gametype["type"] == "tour" and self.sitename == "Microgaming":
                    hand.tablename = info[key]
                else:
                    hand.tablename = re.split(",", info[key])[0]
                    hand.tablename = hand.tablename.strip()
                if "Blaze" in hand.tablename:
                    hand.gametype["fast"] = True
                if self.sitename == "Microgaming":
                    m3 = self.re_Max.search(hand.tablename)
                    if m3 and m3.group("MAX"):
                        if m3.group("MAX") == "HU":
                            hand.maxseats = 2
                        elif len(m3.group("MAX").split(" ")) == 2:
                            hand.maxseats = int(m3.group("MAX").split(" ")[0])
            if key == "BUTTON":
                hand.buttonpos = info[key]
            if key == "MAX" and info[key] is not None:
                seats = int(info[key])
                if seats <= 10:
                    hand.maxseats = int(info[key])

            if key == "PLAY" and info["PLAY"] is not None and info["PLAY"] == "Play":
                #                hand.currency = 'play' # overrides previously set value
                hand.gametype["currency"] = "play"

        if self.re_FastFold.search(hand.handText):
            hand.fastFold = True

        if self.re_Cancelled.search(hand.handText):
            msg = (f"Hand '{hand.handid}' was cancelled.")
            raise FpdbHandPartial(msg)

    def readSummaryInfo(self, summaryInfoList) -> bool:
        log.info("enter method readSummaryInfo.")
        log.debug("Method readSummaryInfo non implemented.")
        return True

    def readButton(self, hand) -> None:
        m = self.re_Button.search(hand.handText)
        if m:
            hand.buttonpos = int(m.group("BUTTON"))
        else:
            log.info("readButton: not found")

    def readPlayerStacks(self, hand) -> None:
        if self.sitename != "Microgaming":
            m = self.re_PlayerInfo1.finditer(hand.handText)
        else:
            m = self.re_PlayerInfo2.finditer(hand.handText)
        for a in m:
            # print a.group('SEAT'), a.group('PNAME'), a.group('CASH')
            hand.addPlayer(int(a.group("SEAT")), a.group("PNAME"), a.group("CASH"))
            if a.group("BUTTON") is not None:
                hand.buttonpos = int(a.group("SEAT"))
        if len(hand.players) == 1:
            msg = (f"Hand '{hand.handid}' was cancelled.")
            raise FpdbHandPartial(msg)

    def markStreets(self, hand) -> None:
        # PREFLOP = ** Dealing down cards **
        # This re fails if,  say, river is missing; then we don't get the ** that starts the river.
        if self.sitename == "Microgaming":
            m = re.search(
                r"\*\* Dealing ca(?P<PREFLOP>.+(?=\*\* Dealing the flop)|.+)"
                r"(\*\* Dealing the flop(?P<FLOP>:\s.+(?=\*\* Dealing the turn)|.+))?"
                r"(\*\* Dealing the turn(?P<TURN>:\s.+(?=\*\* Dealing the river)|.+))?"
                r"(\*\* Dealing the river(?P<RIVER>:\s.+))?",
                hand.handText,
                re.DOTALL,
            )
        else:
            m = re.search(
                r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>.+(?=\*\*\* FLOP \*\*\*)|.+)"
                r"(\*\*\* FLOP \*\*\*(?P<FLOP> \[\S\S\S? \S\S\S? \S\S\S?\].+(?=\*\*\* TURN \*\*\*)|.+))?"
                r"(\*\*\* TURN \*\*\* (?P<TURN>\[\S\S\S?\].+(?=\*\*\* RIVER \*\*\*)|.+))?"
                r"(\*\*\* RIVER \*\*\* (?P<RIVER>\[\S\S\S?\].+))?",
                hand.handText,
                re.DOTALL,
            )
        hand.addStreets(m)

    def readCommunityCards(
        self, hand, street,
    ) -> None:  # street has been matched by markStreets, so exists in this hand
        if street in (
            "FLOP",
            "TURN",
            "RIVER",
        ):  # a list of streets which get dealt community cards (i.e. all but PREFLOP)
            # print "DEBUG readCommunityCards:", street, hand.streets.group(street)
            if self.sitename == "Microgaming":
                m = self.re_Board2.search(hand.streets[street])
                cards = [
                    c.replace("10", "T").strip()
                    for c in m.group("CARDS").replace(" of ", "").split(", ")
                ]
            else:
                m = self.re_Board1.search(hand.streets[street])
                if self.is_ipoker_skin():
                    cards = [
                        c[1:].replace("10", "T") + c[0].lower()
                        for c in m.group("CARDS").split(" ")
                    ]
                else:
                    cards = [
                        c.replace("10", "T").strip()
                        for c in m.group("CARDS").split(" ")
                    ]
            hand.setCommunityCards(street, cards)

    def readAntes(self, hand) -> None:
        log.debug("reading antes")
        m = self.re_Antes.finditer(hand.handText)
        for player in m:
            # ~ logging.debug("hand.addAnte(%s,%s)" %(player.group('PNAME'), player.group('ANTE')))
            self.adjustMergeTourneyStack(
                hand, player.group("PNAME"), player.group("ANTE"),
            )
            hand.addAnte(player.group("PNAME"), player.group("ANTE"))

    def readBlinds(self, hand) -> None:
        liveBlind, bb, sb = True, None, None
        for a in self.re_PostSB.finditer(hand.handText):
            sb = self.clearMoneyString(a.group("SB"))
            if liveBlind:
                self.adjustMergeTourneyStack(hand, a.group("PNAME"), a.group("SB"))
                hand.addBlind(a.group("PNAME"), "small blind", sb)
                if not hand.gametype["sb"]:
                    hand.gametype["sb"] = sb
                liveBlind = False
            elif hand.gametype["type"] == "tour":
                self.adjustMergeTourneyStack(hand, a.group("PNAME"), a.group("SB"))
                if not hand.gametype["bb"]:
                    hand.gametype["bb"] = sb
                    hand.addBlind(a.group("PNAME"), "big blind", sb)
            else:
                # Post dead blinds as ante
                self.adjustMergeTourneyStack(hand, a.group("PNAME"), a.group("SB"))
                hand.addBlind(a.group("PNAME"), "secondsb", sb)
        for a in self.re_PostBB.finditer(hand.handText):
            bb = self.clearMoneyString(a.group("BB"))
            self.adjustMergeTourneyStack(hand, a.group("PNAME"), a.group("BB"))
            if not hand.gametype["bb"]:
                hand.gametype["bb"] = bb
                hand.addBlind(a.group("PNAME"), "big blind", bb)
            else:
                both = Decimal(hand.gametype["bb"]) + old_div(
                    Decimal(hand.gametype["bb"]), 2,
                )
                if both == Decimal(a.group("BB")):
                    hand.addBlind(a.group("PNAME"), "both", bb)
                else:
                    hand.addBlind(a.group("PNAME"), "big blind", bb)

        if self.sitename == "Microgaming":
            for a in self.re_PostBoth2.finditer(hand.handText):
                if self.clearMoneyString(a.group("SBBB")) == hand.gametype["sb"]:
                    hand.addBlind(
                        a.group("PNAME"),
                        "secondsb",
                        self.clearMoneyString(a.group("SBBB")),
                    )
                else:
                    bet = self.clearMoneyString(a.group("SBBB"))
                    amount = str(Decimal(bet) + old_div(Decimal(bet), 2))
                    hand.addBlind(a.group("PNAME"), "both", amount)
            for a in self.re_Action2.finditer(self.re_Hole.split(hand.handText)[0]):
                if a.group("ATYPE") == " went all-in":
                    amount = Decimal(self.clearMoneyString(a.group("BET")))
                    player = a.group("PNAME")
                    if bb is None:
                        hand.addBlind(
                            player, "big blind", self.clearMoneyString(a.group("BET")),
                        )
                        self.allInBlind(hand, "PREFLOP", a, "big blind")
                    elif sb is None:
                        hand.addBlind(
                            player, "small blind", self.clearMoneyString(a.group("BET")),
                        )
                        self.allInBlind(hand, "PREFLOP", a, "small blind")
        else:
            for a in self.re_PostBoth1.finditer(hand.handText):
                self.adjustMergeTourneyStack(hand, a.group("PNAME"), a.group("SBBB"))
                if Decimal(str(hand.sb)) == Decimal(
                    self.clearMoneyString(a.group("SBBB")),
                ):
                    hand.addBlind(
                        a.group("PNAME"),
                        "small blind",
                        self.clearMoneyString(a.group("SBBB")),
                    )
                else:
                    hand.addBlind(
                        a.group("PNAME"), "both", self.clearMoneyString(a.group("SBBB")),
                    )

        # FIXME
        # The following should only trigger when a small blind is missing in a tournament, or the sb/bb is ALL_IN
        # see http://sourceforge.net/apps/mantisbt/fpdb/view.php?id=115
        if hand.gametype["type"] == "tour" and (self.sitename == "Merge" or self.is_ipoker_skin()):
            if hand.gametype["sb"] is None and hand.gametype["bb"] is None:
                hand.gametype["sb"] = "1"
                hand.gametype["bb"] = "2"
            elif hand.gametype["sb"] is None:
                hand.gametype["sb"] = str(old_div(int(Decimal(hand.gametype["bb"])), 2))
            elif hand.gametype["bb"] is None:
                hand.gametype["bb"] = str(int(Decimal(hand.gametype["sb"])) * 2)
            if old_div(int(Decimal(hand.gametype["bb"])), 2) != int(
                Decimal(hand.gametype["sb"]),
            ):
                if old_div(int(Decimal(hand.gametype["bb"])), 2) < int(
                    Decimal(hand.gametype["sb"]),
                ):
                    hand.gametype["bb"] = str(int(Decimal(hand.gametype["sb"])) * 2)
                else:
                    hand.gametype["sb"] = str(
                        old_div(int(Decimal(hand.gametype["bb"])), 2),
                    )

    def readHoleCards(self, hand) -> None:
        #    streets PREFLOP, PREDRAW, and THIRD are special cases beacause
        #    we need to grab hero's cards
        re_HeroCards = self.re_HeroCards1 if self.sitename != "Microgaming" else self.re_HeroCards2
        for street in ("PREFLOP", "DEAL"):
            if street in list(hand.streets.keys()):
                m = re_HeroCards.finditer(hand.streets[street])
                for found in m:
                    #                    if m == None:
                    #                        hand.involved = False
                    #                    else:
                    hand.hero = found.group("PNAME")
                    if self.is_ipoker_skin():
                        newcards = [
                            c[1:].replace("10", "T") + c[0].lower()
                            for c in found.group("NEWCARDS").split(" ")
                        ]
                    elif self.sitename == "Microgaming":
                        newcards = [
                            c.replace("10", "T").strip()
                            for c in found.group("NEWCARDS")
                            .replace(" of ", "")
                            .split(", ")
                        ]
                    else:
                        newcards = [
                            c.replace("10", "T").strip()
                            for c in found.group("NEWCARDS").split(" ")
                        ]
                    hand.addHoleCards(
                        street,
                        hand.hero,
                        closed=newcards,
                        shown=False,
                        mucked=False,
                        dealt=True,
                    )

        for street, text in list(hand.streets.items()):
            if not text or street in ("PREFLOP", "DEAL"):
                continue  # already done these
            m = re_HeroCards.finditer(hand.streets[street])
            for found in m:
                player = found.group("PNAME")
                if found.group("NEWCARDS") is None:
                    newcards = []
                elif self.is_ipoker_skin():
                    newcards = [
                        c[1:].replace("10", "T") + c[0].lower()
                        for c in found.group("NEWCARDS").split(" ")
                    ]
                elif self.sitename == "Microgaming":
                    newcards = [
                        c.replace("10", "T").strip()
                        for c in found.group("NEWCARDS")
                        .replace(" of ", "")
                        .split(", ")
                    ]
                else:
                    newcards = [
                        c.replace("10", "T").strip()
                        for c in found.group("NEWCARDS").split(" ")
                    ]
                if found.group("OLDCARDS") is None:
                    oldcards = []
                elif self.is_ipoker_skin():
                    oldcards = [
                        c[1:].replace("10", "T") + c[0].lower()
                        for c in found.group("OLDCARDS").split(" ")
                    ]
                else:
                    oldcards = [
                        c.replace("10", "T").strip()
                        for c in found.group("OLDCARDS").split(" ")
                    ]

                hand.addHoleCards(
                    street,
                    player,
                    open=newcards,
                    closed=oldcards,
                    shown=False,
                    mucked=False,
                    dealt=False,
                )

    def readAction(self, hand, street) -> None:
        if self.sitename != "Microgaming":
            m = self.re_Action1.finditer(hand.streets[street])
        else:
            m = self.re_Action2.finditer(hand.streets[street])
        curr_pot = Decimal("0")
        for action in m:
            action.groupdict()
            # print "DEBUG: acts: %s" %acts
            if action.group("ATYPE") in (" folds", " Fold", " folded"):
                hand.addFold(street, action.group("PNAME"))
            elif action.group("ATYPE") in (" checks", " Check", " checked"):
                hand.addCheck(street, action.group("PNAME"))
            elif action.group("ATYPE") in (" calls", " Call", " called"):
                hand.addCall(street, action.group("PNAME"), action.group("BET"))
            elif action.group("ATYPE") in (
                " raises",
                " Raise",
                " raised",
                " raised to",
                " Raise to",
            ):
                amount = Decimal(self.clearMoneyString(action.group("BET")))
                if self.sitename == "Merge":
                    hand.addRaiseTo(street, action.group("PNAME"), action.group("BET"))
                elif (
                    self.sitename == "Microgaming"
                    or action.group("ATYPE") == " Raise to"
                ):
                    hand.addCallandRaise(
                        street, action.group("PNAME"), action.group("BET"),
                    )
                elif curr_pot > amount:
                    hand.addCall(street, action.group("PNAME"), action.group("BET"))
                # elif not action.group('RAISETO') and action.group('ATYPE')==' Raise':
                #    hand.addRaiseBy( street, action.group('PNAME'), action.group('BET') )
                else:
                    hand.addRaiseTo(
                        street, action.group("PNAME"), action.group("BET"),
                    )
                curr_pot = amount
            elif action.group("ATYPE") in (" bets", " Bet", " bet"):
                if self.sitename == "Microgaming" and street in (
                    "PREFLOP",
                    "THIRD",
                    "DEAL",
                ):
                    hand.addCallandRaise(
                        street, action.group("PNAME"), action.group("BET"),
                    )
                else:
                    hand.addBet(street, action.group("PNAME"), action.group("BET"))
                curr_pot = Decimal(self.clearMoneyString(action.group("BET")))
            elif action.group("ATYPE") in (" Allin", " went all-in"):
                amount = Decimal(self.clearMoneyString(action.group("BET")))
                hand.addAllIn(street, action.group("PNAME"), action.group("BET"))
                if (
                    curr_pot > amount
                    and curr_pot > Decimal("0")
                    and self.sitename == "Microgaming"
                ):
                    hand.setUncalledBets(False)
                curr_pot = amount
            else:
                log.debug(
                    f"Unimplemented readAction: '{action.group('PNAME')}' '{action.group('ATYPE')}'",
                )

    def allInBlind(self, hand, street, action, actiontype) -> None:
        if street in ("PREFLOP", "DEAL"):
            player = action.group("PNAME")
            if hand.stacks[player] == 0:
                hand.setUncalledBets(True)

    def adjustMergeTourneyStack(self, hand, player, amount) -> None:
        if self.sitename == "Merge":
            amount = Decimal(self.clearMoneyString(amount))
            if hand.gametype["type"] == "tour":
                for p in hand.players:
                    if p[1] == player:
                        stack = Decimal(p[2])
                        stack += amount
                        p[2] = str(stack)
                hand.stacks[player] += amount

    def readCollectPot(self, hand) -> None:
        if self.sitename == "Microgaming":
            for m in self.re_CollectPot2.finditer(hand.handText):
                hand.addCollectPot(
                    player=m.group("PNAME"), pot=re.sub(",", "", m.group("POT")),
                )
        else:
            for m in self.re_CollectPot1.finditer(hand.handText):
                hand.addCollectPot(
                    player=m.group("PNAME"), pot=re.sub(",", "", m.group("POT")),
                )

    def readShowdownActions(self, hand) -> None:
        pass

    def readShownCards(self, hand) -> None:
        found = []
        re_ShownCards = self.re_ShownCards2 if self.sitename == "Microgaming" else self.re_ShownCards1
        for m in re_ShownCards.finditer(hand.handText):
            if m.group("CARDS") is not None and m.group("PNAME") not in found:
                if self.is_ipoker_skin():
                    cards = [
                        c[1:].replace("10", "T") + c[0].lower()
                        for c in m.group("CARDS").split(" ")
                    ]
                elif self.sitename == "Microgaming":
                    cards = [
                        c.replace("10", "T").strip()
                        for c in m.group("CARDS").replace(" of ", "").split(", ")
                    ]
                else:
                    cards = [
                        c.replace("10", "T").strip()
                        for c in m.group("CARDS").split(" ")
                    ]

                (shown, mucked) = (False, False)
                if m.group("SHOWED") in ("shows", "Shows"):
                    shown = True
                elif m.group("SHOWED") in ("mucked", "mucks"):
                    mucked = True
                found.append(m.group("PNAME"))

                # print "DEBUG: hand.addShownCards(%s, %s, %s, %s)" %(cards, m.group('PNAME'), shown, mucked)
                hand.addShownCards(
                    cards=cards, player=m.group("PNAME"), shown=shown, mucked=mucked,
                )

    def readBringIn(self, hand) -> None:
        """Read bring-in for stud games."""
        log.debug("reading bring-in")
        m = self.re_BringIn.search(hand.handText) if hasattr(self, 're_BringIn') else None
        if m:
            self.adjustMergeTourneyStack(hand, m.group("PNAME"), m.group("BRINGIN"))
            hand.addBringIn(m.group("PNAME"), m.group("BRINGIN"))

    def readSTP(self, hand) -> None:
        """Read STP (Sit and Play) information."""
        log.debug("reading STP")
        # Placeholder implementation - PokerTracker format doesn't typically have STP info
        pass

    def readTourneyResults(self, hand) -> None:
        """Read tournament results from hand text."""
        log.debug("reading tournament results")
        # PokerTracker format typically doesn't include tournament results in hand history
        # Tournament results would be in separate summary files
        pass

    def readOther(self, hand) -> None:
        """Read other information from hand that doesn't fit standard categories."""
        log.debug("reading other information")
        pass
