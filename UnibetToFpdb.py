#!/usr/bin/env python
#
#    Copyright 2008-2011, Carl Gherardi
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

from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger

# Unibet HH Format
log = get_logger("parser")


class Unibet(HandHistoryConverter):
    # Class Variables

    sitename = "Unibet"
    filetype = "text"
    codepage = ("utf8", "cp1252", "ISO-8859-1")
    siteId = 30  # Needs to match id entry in Sites database
    sym = {
        "USD": r"\$",
        "CAD": r"\$",
        "T$": "",
        "EUR": "\xe2\x82\xac",
        "GBP": r"\£",
        "play": "",
        "INR": r"\₹",
        "CNY": r"\¥",
    }  # ADD Euro, Sterling, etc HERE
    substitutions = {
        "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP|SC|INR|CNY",  # legal ISO currency codes
        "LS": "\\$|\xe2\x82\xac|\u20ac|\\£|\u20b9|\\¥|",  # legal currency symbols - Euro(cp1252, utf-8)
        "PLYR": r"\s?(?P<PNAME>.+?)",
        "CUR": "(\\$|\xe2\x82\xac|\u20ac||\\£|\u20b9|\\¥|)",
        "BRKTS": r"(\(button\) |\(small blind\) |\(big blind\) |\(button blind\) |\(button\) \(small blind\) |\(small blind/button\) |\(button\) \(big blind\) )?",
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
        "16.00": ("4.00", "8.00"),
        "16": ("4.00", "8.00"),
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
        "150.00": ("50.00", "75.00"),
        "150": ("50.00", "75.00"),
        "200.00": ("50.00", "100.00"),
        "200": ("50.00", "100.00"),
        "400.00": ("100.00", "200.00"),
        "400": ("100.00", "200.00"),
        "500.00": ("100.00", "250.00"),
        "500": ("100.00", "250.00"),
        "600.00": ("150.00", "300.00"),
        "600": ("150.00", "300.00"),
        "800.00": ("200.00", "400.00"),
        "800": ("200.00", "400.00"),
        "1000.00": ("250.00", "500.00"),
        "1000": ("250.00", "500.00"),
        "2000.00": ("500.00", "1000.00"),
        "2000": ("500.00", "1000.00"),
        "4000.00": ("1000.00", "2000.00"),
        "4000": ("1000.00", "2000.00"),
        "10000.00": ("2500.00", "5000.00"),
        "10000": ("2500.00", "5000.00"),
        "20000.00": ("5000.00", "10000.00"),
        "20000": ("5000.00", "10000.00"),
        "40000.00": ("10000.00", "20000.00"),
        "40000": ("10000.00", "20000.00"),
    }

    limits = {"No Limit": "nl", "Pot Limit": "pl", "Fixed Limit": "fl", "Limit": "fl"}
    games = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi/Lo": ("hold", "omahahilo"),
    }
    currencies = {"€": "EUR", "$": "USD", "": "T$", "£": "GBP", "¥": "CNY", "₹": "INR"}

    # Static regexes
    re_GameInfo = re.compile(
        """
          Game\\s\\#(?P<HID>[0-9]+):\\s+Table\\s(?P<CURRENCY>€|$|£)[0-9]+\\s(?P<LIMIT>PL|NL|FL)\\s-\\s(?P<SB>[.0-9]+)/(?P<BB>[.0-9]+)\\s-\\s(?P<GAME>Pot\\sLimit\\sOmaha|No\\sLimit\\sHold\'Em\\sBanzai)\\s-\\s(?P<DATETIME>.*$)
        """.format(),
        re.MULTILINE | re.VERBOSE,
    )

    re_PlayerInfo = re.compile(
        r"""
          Seat\s(?P<SEAT>[0-9]+):\s(?P<PNAME>\w+)\s\((€|$|£)(?P<CASH>[,.0-9]+)\)""".format(),
        re.MULTILINE | re.VERBOSE,
    )

    re_PlayerInfo2 = re.compile(
        r"""
          (?P<SITOUT>\w+)\s\((€|$|£)[,.0-9]+\)\s\(sitting\sout\)""".format(),
        re.MULTILINE | re.VERBOSE,
    )

    re_HandInfo = re.compile(
        r"""
          (?P<TABLE>\sTable\s(€|$|£)[0-9]+\s(PL|NL|FL))""",
        re.MULTILINE | re.VERBOSE,
    )

    re_identify = re.compile(r"Game\s\#\d+:\sTable\s(€|$|£)[0-9]+\s(PL|NL|FL)")
    re_SplitHands = re.compile("(?:\\s?\n){2,}")
    re_TailSplitHands = re.compile("(\n\n\n+)")
    re_Button = re.compile(r"(?P<BUTTON>\w+)\shas\sthe\sbutton", re.MULTILINE)
    re_Board = re.compile(r"\[(?P<CARDS>.+)\]")
    re_Board2 = re.compile(r"\[(?P<C1>\S\S)\] \[(\S\S)?(?P<C2>\S\S) (?P<C3>\S\S)\]")
    re_DateTime1 = re.compile(
        r"""(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)\s(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})""",
        re.MULTILINE,
    )
    re_DateTime2 = re.compile(
        r"""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+)""",
        re.MULTILINE,
    )
    # revised re including timezone (not currently used):
    # re_DateTime     = re.compile("""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+) \(?(?P<TZ>[A-Z0-9]+)""", re.MULTILINE)

    # These used to be compiled per player, but regression tests say
    # we don't have to, and it makes life faster.
    re_PostSB = re.compile(
        r"{PLYR}:\sposts\ssmall\sblind\s{CUR}(?P<SB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_PostBB = re.compile(
        r"{PLYR}:\sposts\sbig\sblind\s{CUR}(?P<BB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_PostBUB = re.compile(
        r"{PLYR}:\sposts\sbutton\sblind\s{CUR}(?P<BUB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_Antes = re.compile(
        r"{PLYR}:\sposts\sthe\sant\s{CUR}(?P<ANTE>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_BringIn = re.compile(
        r"{PLYR}:\sbrings[- ]in(\slow|)\sfo/{CUR}(?P<BRINGIN>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_PostBoth = re.compile(
        r"{PLYR}:\sposts\ssmall\s\&\sbig\sblinds\s{CUR}(?P<SBBB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_PostStraddle = re.compile(
        r"{PLYR}:\sposts\sstraddle\s{CUR}(?P<STRADDLE>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_Action = re.compile(
        r"""
                        {PLYR}:(?P<ATYPE>\sbets|\schecks|\sraises|\scalls|\sfolds|\sdiscards|\sstands\spat)
                        (\s{CUR}(?P<BET>[,.\d]+))?(\sto\s{CUR}(?P<BETTO>[,.\d]+))?
                        \s*(and\sis\sall.in)?
                        (and\shas\sreached\sthe\s[{CUR}\d\.,]+\scap)?
                        (\son|\scards?)?
                        (\s\(disconnect\))?
                        (\s\[(?P<CARDS>.+?)\])?\s*$""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    re_ShowdownAction = re.compile(
        r"{}: shows \[(?P<CARDS>.*)\]".format(substitutions["PLYR"]), re.MULTILINE,
    )
    re_sitsOut = re.compile("^{} sits out".format(substitutions["PLYR"]), re.MULTILINE)
    re_HeroCards = re.compile(
        r"Dealt\sto\s{PLYR}\s(?:\[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(**substitutions),
        re.MULTILINE,
    )
    # re_ShownCards       = re.compile("^Seat (?P<SEAT>[0-9]+): %(PLYR)s %(BRKTS)s(?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]( and (lost|(won|collected) \(%(CUR)s(?P<POT>[.\d]+)\)) with (?P<STRING>.+?)(,\sand\s(won\s\(%(CUR)s[.\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?$" % substitutions, re.MULTILINE)
    # re_CollectPot       = re.compile(r"Seat (?P<SEAT>[0-9]+): %(PLYR)s %(BRKTS)s(collected|showed \[.*\] and (won|collected)) \(?%(CUR)s(?P<POT>[,.\d]+)\)?(, mucked| with.*|)" %  substitutions, re.MULTILINE)
    re_CollectPot = re.compile(
        r"Seat (?P<SEAT>[0-9]+):\s{PLYR}:\sbet\s(€|$|£)(?P<BET>[,.\d]+)\sand\swon\s(€|$|£)[\.0-9]+\W\snet\sresult:\s(€|$|£)(?P<POT>[,.\d]+)".format(**substitutions),
        re.MULTILINE,
    )
    # Vinsand88 cashed out the hand for $2.19 | Cash Out Fee $0.02
    re_CollectPot2 = re.compile(
        r"{PLYR} (collected|cashed out the hand for) {CUR}(?P<POT>[,.\d]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_CashedOut = re.compile(r"cashed\sout\sthe\shand")
    re_WinningRankOne = re.compile(
        r"{PLYR} wins the tournament and receives {CUR}(?P<AMT>[,\.0-9]+) - congratulations!$".format(**substitutions),
        re.MULTILINE,
    )
    re_WinningRankOther = re.compile(
        r"{PLYR} finished the tournament in (?P<RANK>[0-9]+)(st|nd|rd|th) place and received {CUR}(?P<AMT>[,.0-9]+)\.$".format(**substitutions),
        re.MULTILINE,
    )
    re_RankOther = re.compile(
        "{PLYR} finished the tournament in (?P<RANK>[0-9]+)(st|nd|rd|th) place$".format(**substitutions),
        re.MULTILINE,
    )
    re_Cancelled = re.compile(r"Hand\scancelled", re.MULTILINE)
    re_Uncalled = re.compile(
        r"Uncalled\sbet\s\({CUR}(?P<BET>[,.\d]+)\)\sreturned\sto".format(**substitutions),
        re.MULTILINE,
    )
    # APTEM-89 wins the $0.27 bounty for eliminating Hero
    # ChazDazzle wins the 22000 bounty for eliminating berkovich609
    # JKuzja, vecenta split the $50 bounty for eliminating ODYSSES
    re_Bounty = re.compile(
        r"{PLYR} (?P<SPLIT>split|wins) the {CUR}(?P<AMT>[,\.0-9]+) bounty for eliminating (?P<ELIMINATED>.+?)$".format(**substitutions),
        re.MULTILINE,
    )
    # Amsterdam71 wins $19.90 for eliminating MuKoJla and their own bounty increases by $19.89 to $155.32
    # Amsterdam71 wins $4.60 for splitting the elimination of Frimble11 and their own bounty increases by $4.59 to $41.32
    # Amsterdam71 wins the tournament and receives $230.36 - congratulations!
    re_Progressive = re.compile(
        r"""
                        {PLYR}\swins\s{CUR}(?P<AMT>[,\.0-9]+)\s
                        for\s(splitting\sthe\selimination\sof|eliminating)\s(?P<ELIMINATED>.+?)\s
                        and\stheir\sown\sbounty\sincreases\sby\s{CUR}(?P<INCREASE>[\.0-9]+)\sto\s{CUR}(?P<ENDAMT>[\.0-9]+)$""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    re_Rake = re.compile(
        r"""
                        Total\spot\s{CUR}(?P<POT>[,\.0-9]+)(.+?)?\s\|\sRake\s{CUR}(?P<RAKE>[,\.0-9]+)""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_STP = re.compile(
        r"""
                        STP\sadded:\s{CUR}(?P<AMOUNT>[,\.0-9]+)""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    def compilePlayerRegexs(self, hand) -> None:
        players = {player[1] for player in hand.players}
        if not players <= self.compiledPlayers:  # x <= y means 'x is subset of y'
            self.compiledPlayers = players
            player_re = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"
            subst = {
                "PLYR": player_re,
                "BRKTS": r"(\(button\) |\(small\sblind\) |\(big\blind\) |\(button\) \(small\sblind\) |\(button\) \(big\sblind\) )?",
                "CUR": "(\\$|\xe2\x82\xac|\u20ac||\\£|)",
            }

            self.re_HeroCards = re.compile(
                r"Dealt\sto\s{PLYR}(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(**subst),
                re.MULTILINE,
            )
            self.re_ShownCards = re.compile(
                r"Seat\s(?P<SEAT>[0-9]+):\s{PLYR}\s{BRKTS}(?P<SHOWED>showed|mucked)\s\[(?P<CARDS>.*)\](\sand\s(lost|(won|collected)\s \({CUR}(?P<POT>[,\.\d]+)\))\swith\s(?P<STRING>.+?)(,\sand\s(won\s\({CUR}[\.\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?$".format(**subst),
                re.MULTILINE,
            )

    def readSupportedGames(self):
        return [
            ["ring", "hold", "nl"],
            ["ring", "hold", "pl"],
            ["ring", "hold", "fl"],
            ["ring", "hold", "pn"],
            ["ring", "stud", "fl"],
            ["ring", "draw", "fl"],
            ["ring", "draw", "pl"],
            ["ring", "draw", "nl"],
            ["tour", "hold", "nl"],
            ["tour", "hold", "pl"],
            ["tour", "hold", "fl"],
            ["tour", "hold", "pn"],
            ["tour", "stud", "fl"],
            ["tour", "draw", "fl"],
            ["tour", "draw", "pl"],
            ["tour", "draw", "nl"],
        ]

    def determineGameType(self, handText):
        info = {}
        m = self.re_GameInfo.search(handText)
        if not m:
            tmp = handText[0:200]
            log.error(f"determine Game Type failed: '{tmp}'")
            raise FpdbParseError

        mg = m.groupdict()
        if "LIMIT" in mg:
            # print(mg['LIMIT'])
            if mg["LIMIT"] == "NL":
                info["limitType"] = self.limits["No Limit"]
            elif mg["LIMIT"] == "PL":
                info["limitType"] = self.limits["Pot Limit"]

            # info['limitType'] = self.limits[mg['LIMIT']]
        if "GAME" in mg:
            log.debug(f"Game type detected: {mg['GAME']}")
            if mg["GAME"] == "No Limit Hold'Em Banzai":
                info["base"] = "hold"
                info["category"] = "holdem"
                info["type"] = "ring"
                info["split"] = False
            elif mg["GAME"] == "Pot Limit Omaha":
                info["base"] = "hold"
                info["category"] = "omahahi"
                info["type"] = "ring"
                info["split"] = False
            # (info['base'], info['category']) = self.games[mg['GAME']]
        if "SB" in mg and mg["SB"] is not None:
            info["sb"] = mg["SB"]
        if "BB" in mg and mg["BB"] is not None:
            info["bb"] = mg["BB"]
        if "BUB" in mg and mg["BUB"] is not None:
            info["sb"] = "0"
            info["bb"] = mg["BUB"]
        if "CURRENCY1" in mg and mg["CURRENCY1"] is not None:
            info["currency"] = self.currencies[mg["CURRENCY1"]]
        elif "CURRENCY" in mg:
            info["currency"] = self.currencies[mg["CURRENCY"]]

        # if 'Zoom' in mg['TITLE'] or 'Rush' in mg['TITLE']:
        #     info['fast'] = True
        # else:
        #     info['fast'] = False
        # if 'Home' in mg['TITLE']:
        #     info['homeGame'] = True
        # else:
        #     info['homeGame'] = False
        # if 'CAP' in mg and mg['CAP'] is not None:
        #     info['buyinType'] = 'cap'
        # else:
        #     info['buyinType'] = 'regular'
        # if 'SPLIT' in mg and mg['SPLIT'] == 'Split':
        #     info['split'] = True
        # else:
        #     info['split'] = False
        # if 'SITE' in mg:
        #     if mg['SITE'] == 'PokerMaster':
        #         self.sitename = "PokerMaster"
        #         self.siteId   = 25
        #         m1  = self.re_HandInfo.search(handText,re.DOTALL)
        #         if m1 and '_5Cards_' in m1.group('TABLE'):
        #             info['category'] = '5_omahahi'
        #     elif mg['SITE'] == 'Run It Once Poker':
        #         self.sitename = "Run It Once Poker"
        #         self.siteId   = 26
        #     elif mg['SITE'] == 'BetOnline':
        #         self.sitename = 'BetOnline'
        #         self.siteId = 19
        #     elif mg['SITE'] == 'PokerBros':
        #         self.sitename = 'PokerBros'
        #         self.siteId = 29

        # if 'TOURNO' in mg and mg['TOURNO'] is None:
        #     info['type'] = 'ring'
        # else:
        #     info['type'] = 'tour'
        #     if 'ZOOM' in mg['TOUR']:
        #         info['fast'] = True

        if info.get("currency") in ("T$", None) and info["type"] == "ring":
            info["currency"] = "play"

        if info["limitType"] == "fl" and info["bb"] is not None:
            if info["type"] == "ring":
                try:
                    info["sb"] = self.Lim_Blinds[mg["BB"]][0]
                    info["bb"] = self.Lim_Blinds[mg["BB"]][1]
                except KeyError:
                    tmp = handText[0:200]
                    log.exception(f"Lim_Blinds has no lookup for '{mg['BB']}' - '{tmp}'")
                    raise FpdbParseError
            else:
                info["sb"] = str((Decimal(mg["SB"]) / 2).quantize(Decimal("0.01")))
                info["bb"] = str(Decimal(mg["SB"]).quantize(Decimal("0.01")))
        log.info(f"determine Game Type failed: '{info}'")
        return info

    def readHandInfo(self, hand) -> None:
        # First check if partial
        if hand.handText.count("*** Summary ***") != 1:
            msg = "Hand is not cleanly split into pre and post Summary"
            raise FpdbHandPartial(
                (msg),
            )

        info = {}
        m = self.re_HandInfo.search(hand.handText, re.DOTALL)
        m2 = self.re_GameInfo.search(hand.handText)
        if m is None or m2 is None:
            tmp = hand.handText[0:200]
            log.error(f"read Hand Info failed: '{tmp}'")
            raise FpdbParseError

        info.update(m.groupdict())
        info.update(m2.groupdict())

        log.debug(f"readHandInfo: {info}")
        for key in info:
            if key == "DATETIME":
                # 2008/11/12 10:00:48 CET [2008/11/12 4:00:48 ET] # (both dates are parsed so ET date overrides the other)
                # 2008/08/17 - 01:14:43 (ET)
                # 2008/09/07 06:23:14 ET
                datetimestr = "00:00:00 2000/01/01"  # default used if time not found
                if self.siteId == 26:
                    m2 = self.re_DateTime2.finditer(info[key])

                else:
                    m1 = self.re_DateTime1.finditer(info[key])
                    for a in m1:
                        datetimestr1 = (
                            str(a.group("H"))
                            + ":"
                            + str(a.group("MIN"))
                            + ":"
                            + str(a.group("S"))
                        )
                        datetimestr2 = (
                            str(a.group("Y"))
                            + "/"
                            + str(a.group("M"))
                            + "/"
                            + str(a.group("D"))
                        )
                        datetimestr = datetimestr2 + " " + datetimestr1
                        # print("datetimestr", datetimestr)
                        # tz = a.group('TZ')  # just assume ET??
                        # print ("   tz = ", tz, " datetime =", datetimestr)
                    hand.startTime = datetime.datetime.strptime(
                        datetimestr, "%Y/%m/%d %H:%M:%S",
                    )  # also timezone at end, e.g. " ET"
                    # hand.startTime = HandHistoryConverter.changeTimezone(hand.startTime, "ET", "UTC")

            if key == "HID":
                hand.handid = info[key]
            if key == "TOURNO":
                hand.tourNo = info[key]
            if key == "BUYIN" and hand.tourNo is not None:
                log.debug(f"info['BUYIN']: {info['BUYIN']}")
                log.debug(f"info['BIAMT']: {info['BIAMT']}")
                log.debug(f"info['BIRAKE']: {info['BIRAKE']}")
                log.debug(f"info['BOUNTY']: {info['BOUNTY']}")

                if info[key].strip() == "Freeroll":
                    hand.buyin = 0
                    hand.fee = 0
                    hand.buyinCurrency = "FREE"
                elif info[key].strip() == "":
                    hand.buyin = 0
                    hand.fee = 0
                    hand.buyinCurrency = "NA"
                else:
                    if info[key].find("$") != -1:
                        hand.buyinCurrency = "USD"
                    elif info[key].find("£") != -1:
                        hand.buyinCurrency = "GBP"
                    elif info[key].find("€") != -1:
                        hand.buyinCurrency = "EUR"
                    elif info[key].find("₹") != -1:
                        hand.buyinCurrency = "INR"
                    elif info[key].find("¥") != -1:
                        hand.buyinCurrency = "CNY"
                    elif info[key].find("FPP") != -1 or info[key].find("SC") != -1:
                        hand.buyinCurrency = "PSFP"
                    elif re.match("^[0-9+]*$", info[key].strip()):
                        hand.buyinCurrency = "play"
                    else:
                        # FIXME: handle other currencies, play money
                        log.error(
                            f"Failed to detect currency. Hand ID: {hand.handid}: '{info[key]}'",
                        )
                        raise FpdbParseError

                    info["BIAMT"] = info["BIAMT"].strip("$€£FPPSC₹")

                    if hand.buyinCurrency != "PSFP":
                        if info["BOUNTY"] is not None:
                            # There is a bounty, Which means we need to switch BOUNTY and BIRAKE values
                            tmp = info["BOUNTY"]
                            info["BOUNTY"] = info["BIRAKE"]
                            info["BIRAKE"] = tmp
                            info["BOUNTY"] = info["BOUNTY"].strip(
                                "$€£₹",
                            )  # Strip here where it isn't 'None'
                            hand.koBounty = int(100 * Decimal(info["BOUNTY"]))
                            hand.isKO = True
                        else:
                            hand.isKO = False

                        info["BIRAKE"] = info["BIRAKE"].strip("$€£₹")

                        hand.buyin = (
                            int(100 * Decimal(info["BIAMT"])) + hand.koBounty
                        )
                        hand.fee = int(100 * Decimal(info["BIRAKE"]))
                    else:
                        hand.buyin = int(100 * Decimal(info["BIAMT"]))
                        hand.fee = 0
                if "Zoom" in info["TITLE"] or "Rush" in info["TITLE"]:
                    hand.isFast = True
                else:
                    hand.isFast = False
                if "Home" in info["TITLE"]:
                    hand.isHomeGame = True
                else:
                    hand.isHomeGame = False
            if key == "LEVEL":
                hand.level = info[key]
            if key == "SHOOTOUT" and info[key] is not None:
                hand.isShootout = True
            if key == "TABLE":
                hand.tablename = info[key]
                # if info['TOURNO'] is not None and info['HIVETABLE'] is not None:
                #     hand.tablename = info['HIVETABLE']
                # elif hand.tourNo != None and len(tablesplit)>1:
                #     hand.tablename = tablesplit[1]
                # else:
                #     hand.tablename = info[key]
            if key == "BUTTON":
                hand.buttonpos = info[key]
            if key == "MAX" and info[key] is not None:
                hand.maxseats = int(info[key])
        log.info(f"read Hand Info: {hand}")
        if self.re_Cancelled.search(hand.handText):
            msg = (f"Hand '{hand.handid}' was cancelled.")
            raise FpdbHandPartial(msg)

    def readButton(self, hand) -> None:
        pre, post = hand.handText.split("*** Summary ***")
        m = self.re_Button.search(hand.handText)
        m2 = self.re_PlayerInfo.finditer(pre)
        if m:
            for b in m2:
                if b.group("PNAME") == m.group("BUTTON"):
                    hand.buttonpos = int(b.group("SEAT"))
                    log.info(f"read button: {int(b.group('SEAT'))}")
        else:
            log.info("readButton: not found")

    def readPlayerStacks(self, hand) -> None:
        pre, post = hand.handText.split("*** Summary ***")
        m = self.re_PlayerInfo.finditer(pre)
        m2 = self.re_PlayerInfo2.finditer(pre)
        for b in m2:
            for a in m:
                if a.group("PNAME") == b.group("SITOUT"):
                    hand.addPlayer(
                        int(a.group("SEAT")),
                        a.group("PNAME"),
                        self.clearMoneyString(a.group("CASH")),
                        None,
                        int(a.group("SEAT")),
                        # self.clearMoneyString(a.group('BOUNTY'))
                    )
                    log.info(
                        f"read Player Stacks: '{int(a.group('SEAT'))}' '{a.group('PNAME')}' '{self.clearMoneyString(a.group('CASH'))}' '{None}' '{int(a.group('SEAT'))}'",
                    )
                    break
                if a.group("PNAME") != b.group("SITOUT"):
                    hand.addPlayer(
                        int(a.group("SEAT")),
                        a.group("PNAME"),
                        self.clearMoneyString(a.group("CASH")),
                        None,
                    )
                    log.info(
                        f"read Player Stacks: '{int(a.group('SEAT'))}' '{a.group('PNAME')}' '{self.clearMoneyString(a.group('CASH'))}' '{None}'",
                    )

    def markStreets(self, hand) -> None:
        # There is no marker between deal and draw in Stars single draw games
        #  this upsets the accounting, incorrectly sets handsPlayers.cardxx and
        #  in consequence the mucked-display is incorrect.
        # Attempt to fix by inserting a DRAW marker into the hand text attribute
        # PREFLOP = ** Dealing down cards **
        # This re fails if,  say, river is missing; then we don't get the ** that starts the river.
        m = re.search(
            r"\*\*\*\sHole\scards\s\*\*\*(?P<PREFLOP>(.+(?P<FLOPET>\[\S\S\]))?.+(?=\*\*\*\sFlop\s\*\*\*)|.+)"
            r"(\*\*\*\sFlop\s\*\*\*(?P<FLOP>(\[\S\S\s])?\[(\S\S?)?\S\S\S\S\].+(?=\*\*\*\sTurn\s\*\*\*)|.+))?"
            r"(\*\*\*\sTurn\s\*\*\*\s\[\S\S \S\S \S\S\](?P<TURN>\[\S\S\].+(?=\*\*\*\sRiver\s\*\*\*)|.+))?"
            r"(\*\*\*\sRiver\s\*\*\*\s\[\S\S \S\S \S\S\]?\s\[?\S\S\]\s(?P<RIVER>\[\S\S\].+))?",
            hand.handText,
            re.DOTALL,
        )
        hand.addStreets(m)
        log.info(f"read hand add streets: {hand}")

    def readCommunityCards(
        self, hand, street,
    ) -> None:  # street has been matched by markStreets, so exists in this hand
        m = self.re_Board.search(hand.streets[street])
        if m:
            hand.setCommunityCards(street, m.group("CARDS").split(" "))
            log.info(f"read set Community Cards: '{street}'")
        else:
            log.error("read set Community Cards: none")

    def readAntes(self, hand) -> None:
        log.debug("reading antes")
        m = self.re_Antes.finditer(hand.handText)
        for player in m:
            log.info(f"hand add Ante({player.group('PNAME')},{player.group('ANTE')})")
            hand.addAnte(
                player.group("PNAME"), self.clearMoneyString(player.group("ANTE")),
            )

    def readBringIn(self, hand) -> None:
        m = self.re_BringIn.search(hand.handText, re.DOTALL)
        if m:
            log.info(f"readBringIn: {m.group('PNAME')} for {m.group('BRINGIN')}")
            hand.addBringIn(m.group("PNAME"), self.clearMoneyString(m.group("BRINGIN")))

    def readBlinds(self, hand) -> None:
        liveBlind = True
        for a in self.re_PostSB.finditer(hand.handText):
            if liveBlind:
                hand.addBlind(
                    a.group("PNAME"),
                    "small blind",
                    self.clearMoneyString(a.group("SB")),
                )
                log.info(
                    f"read Blinds: '{a.group('PNAME')}' for '{self.clearMoneyString(a.group('SB'))}'",
                )
                liveBlind = False
            else:
                names = [p[1] for p in hand.players]
                if "Big Blind" in names or "Small Blind" in names or "Dealer" in names:
                    hand.addBlind(
                        a.group("PNAME"),
                        "small blind",
                        self.clearMoneyString(a.group("SB")),
                    )
                    log.info(
                        f"read Blinds: '{a.group('PNAME')}' for '{self.clearMoneyString(a.group('SB'))}'",
                    )
                else:
                    # Post dead blinds as ante
                    hand.addBlind(
                        a.group("PNAME"),
                        "secondsb",
                        self.clearMoneyString(a.group("SB")),
                    )
                    log.info(
                        f"read Blinds: '{a.group('PNAME')}' for '{self.clearMoneyString(a.group('SB'))}'",
                    )
        for a in self.re_PostBB.finditer(hand.handText):
            hand.addBlind(
                a.group("PNAME"), "big blind", self.clearMoneyString(a.group("BB")),
            )
            log.info(
                f"readBlinds: '{a.group('PNAME')}' for '{self.clearMoneyString(a.group('BB'))}'",
            )
        for a in self.re_PostBoth.finditer(hand.handText):
            hand.addBlind(
                a.group("PNAME"), "both", self.clearMoneyString(a.group("SBBB")),
            )
            log.info(
                f"readBlinds: '{a.group('PNAME')}' for '{self.clearMoneyString(a.group('SBBB'))}'",
            )

        for a in self.re_PostStraddle.finditer(hand.handText):
            hand.addBlind(
                a.group("PNAME"), "straddle", self.clearMoneyString(a.group("STRADDLE")),
            )
            log.info(
                f"read Blinds: '{a.group('PNAME')}' for '{self.clearMoneyString(a.group('STRADDLE'))}'",
            )
        for a in self.re_PostBUB.finditer(hand.handText):
            hand.addBlind(
                a.group("PNAME"), "button blind", self.clearMoneyString(a.group("BUB")),
            )
            log.info(
                f"read Blinds: '{a.group('PNAME')}' for '{self.clearMoneyString(a.group('BUB'))}'",
            )

    def readHoleCards(self, hand) -> None:
        #    streets PREFLOP, PREDRAW, and THIRD are special cases beacause
        #    we need to grab hero's cards
        for street in ("PREFLOP", "DEAL"):
            if street in hand.streets:
                log.debug(f"Processing street: {street}")
                m = self.re_HeroCards.finditer(hand.streets[street])
                log.debug(f"Match object for street {street}: {m}")

                for found in m:
                    #                    if m == None:
                    #                        hand.involved = False
                    #                    else:
                    hand.hero = found.group("PNAME")
                    log.info(f"read HoleCards: '{found.group('PNAME')}'")
                    if "cards" not in found.group("NEWCARDS"):
                        newcards = found.group("NEWCARDS").split(" ")
                        hand.addHoleCards(
                            street,
                            hand.hero,
                            closed=newcards,
                            shown=False,
                            mucked=False,
                            dealt=True,
                        )

    def readAction(self, hand, street) -> None:
        s = street + "2" if hand.gametype["split"] and street in hand.communityStreets else street
        if not hand.streets[s]:
            return
        m = self.re_Action.finditer(hand.streets[s])
        for action in m:
            acts = action.groupdict()
            log.error(f"read actions: {street} acts: {acts}")
            if action.group("ATYPE") == " folds":
                hand.addFold(street, action.group("PNAME"))
            elif action.group("ATYPE") == " checks":
                hand.addCheck(street, action.group("PNAME"))
            elif action.group("ATYPE") == " calls":
                hand.addCall(
                    street,
                    action.group("PNAME"),
                    self.clearMoneyString(action.group("BET")),
                )
            elif action.group("ATYPE") == " raises":
                if action.group("BETTO") is not None:
                    hand.addRaiseTo(
                        street,
                        action.group("PNAME"),
                        self.clearMoneyString(action.group("BETTO")),
                    )
                elif action.group("BET") is not None:
                    hand.addCallandRaise(
                        street,
                        action.group("PNAME"),
                        self.clearMoneyString(action.group("BET")),
                    )
            elif action.group("ATYPE") == " bets":
                hand.addBet(
                    street,
                    action.group("PNAME"),
                    self.clearMoneyString(action.group("BET")),
                )
            elif action.group("ATYPE") == " discards":
                hand.addDiscard(
                    street,
                    action.group("PNAME"),
                    action.group("BET"),
                    action.group("CARDS"),
                )
            elif action.group("ATYPE") == " stands pat":
                hand.addStandsPat(street, action.group("PNAME"), action.group("CARDS"))
            else:
                log.info(
                    f"Unimplemented readAction: '{action.group('PNAME')}' '{action.group('ATYPE')}'",
                )

    def readShowdownActions(self, hand) -> None:
        for shows in self.re_ShowdownAction.finditer(hand.handText):
            cards = shows.group("CARDS").split(" ")
            log.debug(f"read Showdown Actions('{cards}','{shows.group('PNAME')}')")
            hand.addShownCards(cards, shows.group("PNAME"))
            log.info(f"read Showdown Actions('{cards}','{shows.group('PNAME')}')")

    def readTourneyResults(self, hand) -> None:
        """Reads knockout bounties and add them to the koCounts dict."""

    def readCollectPot(self, hand) -> None:
        hand.setUncalledBets(True)
        for m in self.re_CollectPot.finditer(hand.handText):
            hand.addCollectPot(
                player=m.group("PNAME"), pot=str(Decimal(m.group("POT"))),
            )
            log.info(
                f"read Collect Pot: '{m.group('PNAME')}' for '{Decimal(m.group('POT'))!s}'",
            )

    def readShownCards(self, hand) -> None:
        pass

    @staticmethod
    def getTableTitleRe(type, table_name=None, tournament=None, table_number=None) -> None:
        pass
