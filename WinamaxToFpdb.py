#!/usr/bin/env python

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

import datetime
import platform
import re
from decimal import Decimal

# import L10n
# _ = L10n.get_translation()
from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger

# Winamax HH Format
log = get_logger("parser")


class Winamax(HandHistoryConverter):
    def Trace(self):
        def my_f(*args, **kwds):
            log.debug(f"entering {self.__name__}")
            result = self(*args, **kwds)
            log.debug(f"exiting {self.__name__}")
            return result

        my_f.__name = self.__name__
        my_f.__doc__ = self.__doc__
        return my_f

    filter = "Winamax"
    siteName = "Winamax"
    filetype = "text"
    codepage = ("utf8", "cp1252")
    siteId = 15  # Needs to match id entry in Sites database

    mixes = {}  # Legal mixed games
    sym = {
        "USD": r"\$",
        "CAD": r"\$",
        "T$": "",
        "EUR": "\xe2\x82\xac|\u20ac",
        "GBP": "\xa3",
        "play": "",
    }
    # ADD Euro, Sterling, etc HERE
    substitutions = {
        "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP",  # legal ISO currency codes
        "LS": "\\$|\xe2\x82\xac|\u20ac|",  # legal currency symbols - Euro(cp1252, utf-8)
    }

    limits = {"no limit": "nl", "pot limit": "pl", "fixed limit": "fl"}

    games = {  # base, category
        "Holdem": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha5": ("hold", "5_omahahi"),
        "5 Card Omaha": ("hold", "5_omahahi"),
        "5 Card Omaha Hi/Lo": ("hold", "5_omahahi"),  # incorrect in file
        "Omaha Hi/Lo": ("hold", "omahahilo"),
        "Omaha8": ("hold", "omahahilo"),
        "7-Card Stud": ("stud", "studhi"),
        "7stud": ("stud", "studhi"),
        "7-Card Stud Hi/Lo": ("stud", "studhilo"),
        "7stud8": ("stud", "studhilo"),
        "Razz": ("stud", "razz"),
        "2-7 Triple Draw": ("draw", "27_3draw"),
        "Lowball27": ("draw", "27_3draw"),
    }

    # Static regexes
    # ***** End of hand R5-75443872-57 *****
    re_identify = re.compile(
        r'Winamax\sPoker\s\-\s(CashGame|Go\sFast|HOLD\-UP|Tournament\s")',
    )
    re_SplitHands = re.compile(r"\n\n")

    re_HandInfo = re.compile(
        """
            \\s*Winamax\\sPoker\\s-\\s
            (?P<RING>(CashGame|Go\\sFast\\s"[^"]+"|HOLD\\-UP\\s"[^"]+"))?
            (?P<TOUR>Tournament\\s
            (?P<TOURNAME>.+)?\\s
            buyIn:\\s(?P<BUYIN>(?P<BIAMT>[{LS}\\d\\,.]+)?(\\s\\+?\\s|-)(?P<BIRAKE>[{LS}\\d\\,.]+)?\\+?(?P<BOUNTY>[{LS}\\d\\.]+)?\\s?(?P<TOUR_ISO>{LEGAL_ISO})?|(?P<FREETICKET>[\\sa-zA-Z]+))?\\s
            (level:\\s(?P<LEVEL>\\d+))?
            .*)?
            \\s-\\sHandId:\\s\\#(?P<HID1>\\d+)-(?P<HID2>\\d+)-(?P<HID3>\\d+)\\s-\\s  # REB says: HID3 is the correct hand number
            (?P<GAME>Holdem|Omaha|Omaha5|Omaha8|5\\sCard\\sOmaha|5\\sCard\\sOmaha\\sHi/Lo|Omaha\\sHi/Lo|7\\-Card\\sStud|7stud|7\\-Card\\sStud\\sHi/Lo|7stud8|Razz|2\\-7\\sTriple\\sDraw|Lowball27)\\s
            (?P<LIMIT>fixed\\slimit|no\\slimit|pot\\slimit)\\s
            \\(
            ((({LS})?(?P<ANTE>[.0-9]+)({LS})?)/)?
            (({LS})?(?P<SB>[.0-9]+)({LS})?)/
            (({LS})?(?P<BB>[.0-9]+)({LS})?)
            \\)\\s-\\s
            (?P<DATETIME>.*)
            Table:?\\s\'(?P<TABLE>[^(]+)
            (.(?P<TOURNO>\\d+).\\#(?P<TABLENO>\\d+))?.*
            \'
            \\s(?P<MAXPLAYER>\\d+)\\-max
            \\s(?P<MONEY>\\(real\\smoney\\))?
            """.format(**substitutions),
        re.MULTILINE | re.DOTALL | re.VERBOSE,
    )

    re_TailSplitHands = re.compile(r"\n\s*\n")
    re_Button = re.compile(r"Seat\s#(?P<BUTTON>\d+)\sis\sthe\sbutton")
    re_Board = re.compile(r"\[(?P<CARDS>.+)\]")
    re_Total = re.compile(
        r"Total pot (?P<TOTAL>[\.\d]+).*(No rake|Rake (?P<RAKE>[\.\d]+))".format(),
    )
    re_Mixed = re.compile(r"_(?P<MIXED>10games|8games|horse)_")
    re_HUTP = re.compile(
        r"Hold\-up\sto\sPot:\stotal\s(({LS})?(?P<AMOUNT>[.0-9]+)({LS})?)".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    # 2010/09/21 03:10:51 UTC
    re_DateTime = re.compile(
        r"""
            (?P<Y>[0-9]{4})/
            (?P<M>[0-9]+)/
            (?P<D>[0-9]+)\s
            (?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)\s
            UTC
            """,
        re.MULTILINE | re.VERBOSE,
    )

    # Seat 1: some_player (5€)
    # Seat 2: some_other_player21 (6.33€)
    # Seat 6: I want fold (147894, 29.25€ bounty)
    re_PlayerInfo = re.compile(
        r"Seat\s(?P<SEAT>[0-9]+):\s(?P<PNAME>.*)\s\(({LS})?(?P<CASH>[.0-9]+)({LS})?(,\s({LS})?(?P<BOUNTY>[.0-9]+)({LS})?\sbounty)?\)".format(**substitutions),
    )
    re_PlayerInfoSummary = re.compile(
        r"Seat\s(?P<SEAT>[0-9]+):\s(?P<PNAME>.+?)\s".format(),
    )

    def compilePlayerRegexs(self, hand) -> None:
        players = {player[1] for player in hand.players}
        if not players <= self.compiledPlayers:  # x <= y means 'x is subset of y'
            # we need to recompile the player regexs.
            # TODO: should probably rename re_HeroCards and corresponding method,
            #    since they are used to find all cards on lines starting with "Dealt to:"
            #    They still identify the hero.
            self.compiledPlayers = players
            # ANTES/BLINDS
            # helander2222 posts blind ($0.25), lopllopl posts blind ($0.50).
            player_re = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"
            subst = {"PLYR": player_re, "CUR": self.sym[hand.gametype["currency"]]}
            self.re_PostSB = re.compile(
                r"{PLYR} posts small blind ({CUR})?(?P<SB>[\.0-9]+)({CUR})?(?! out of position)".format(**subst),
                re.MULTILINE,
            )
            self.re_PostBB = re.compile(
                r"{PLYR} posts big blind ({CUR})?(?P<BB>[\.0-9]+)({CUR})?".format(**subst),
                re.MULTILINE,
            )
            self.re_DenySB = re.compile("(?P<PNAME>.*) deny SB".format(), re.MULTILINE)
            self.re_Antes = re.compile(
                r"^{PLYR} posts ante ({CUR})?(?P<ANTE>[\.0-9]+)({CUR})?".format(**subst),
                re.MULTILINE,
            )
            self.re_BringIn = re.compile(
                r"^{PLYR} (brings in|bring\-in) ({CUR})?(?P<BRINGIN>[\.0-9]+)({CUR})?".format(**subst),
                re.MULTILINE,
            )
            self.re_PostBoth = re.compile(
                r"(?P<PNAME>.*): posts small \& big blind \( ({CUR})?(?P<SBBB>[\.0-9]+)({CUR})?\)".format(**subst),
            )
            self.re_PostDead = re.compile(
                r"(?P<PNAME>.*) posts dead blind \(({CUR})?(?P<DEAD>[\.0-9]+)({CUR})?\)".format(**subst),
                re.MULTILINE,
            )
            self.re_PostSecondSB = re.compile(
                r"{PLYR} posts small blind ({CUR})?(?P<SB>[\.0-9]+)({CUR})? out of position".format(**subst),
                re.MULTILINE,
            )
            self.re_HeroCards = re.compile(
                r"Dealt\sto\s{PLYR}(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(**subst),
            )

            # no discards action observed yet
            self.re_Action = re.compile(
                r"(, )?(?P<PNAME>.*?)(?P<ATYPE> bets| checks| raises| calls| folds| stands\spat)( \-?({CUR})?(?P<BET>[\d\.]+)({CUR})?)?( to ({CUR})?(?P<BETTO>[\d\.]+)({CUR})?)?( and is all-in)?".format(**subst),
            )
            self.re_ShowdownAction = re.compile(
                "(?P<PNAME>[^\\(\\)\n]*) (\\((small blind|big blind|button)\\) )?shows \\[(?P<CARDS>.+)\\]",
            )

            self.re_CollectPot = re.compile(
                r"\s*(?P<PNAME>.*)\scollected\s({CUR})?(?P<POT>[\.\d]+)({CUR})?.*".format(**subst),
            )
            self.re_ShownCards = re.compile(
                r"^Seat (?P<SEAT>[0-9]+): {PLYR} (\((small blind|big blind|button)\) )?showed \[(?P<CARDS>.*)\].+? with (?P<STRING>.*)".format(**subst),
                re.MULTILINE,
            )

    def readSupportedGames(self):
        return [
            ["ring", "hold", "fl"],
            ["ring", "hold", "nl"],
            ["ring", "hold", "pl"],
            ["ring", "stud", "fl"],
            ["ring", "draw", "fl"],
            ["ring", "draw", "pl"],
            ["ring", "draw", "nl"],
            ["tour", "hold", "fl"],
            ["tour", "hold", "nl"],
            ["tour", "hold", "pl"],
            ["tour", "stud", "fl"],
            ["tour", "draw", "fl"],
            ["tour", "draw", "pl"],
            ["tour", "draw", "nl"],
        ]

    def determineGameType(self, handText):
        # Inspect the handText and return the gametype dict
        # gametype dict is: {'limitType': xxx, 'base': xxx, 'category': xxx}
        info = {}

        m = self.re_HandInfo.search(handText)
        if not m:
            tmp = handText[0:200]
            log.error(f"determine Game Type failed: '{tmp}'")
            raise FpdbParseError

        mg = m.groupdict()

        if mg.get("TOUR"):
            info["type"] = "tour"
            info["currency"] = "T$"
        elif mg.get("RING"):
            info["type"] = "ring"

            info["currency"] = "EUR" if mg.get("MONEY") else "play"
            info["fast"] = "Go Fast" in mg.get("RING")
        if "LIMIT" in mg:
            if mg["LIMIT"] in self.limits:
                info["limitType"] = self.limits[mg["LIMIT"]]
            else:
                tmp = handText[0:100]
                log.error(f"Limit not found in {tmp}.")
                raise FpdbParseError
        if "GAME" in mg:
            (info["base"], info["category"]) = self.games[mg["GAME"]]
        if m := self.re_Mixed.search(self.in_path):
            info["mix"] = self.mixes[m.groupdict()["MIXED"]]
        if "SB" in mg:
            info["sb"] = mg["SB"]
        if "BB" in mg:
            info["bb"] = mg["BB"]

        if info["limitType"] == "fl" and info["bb"] is not None:
            info["sb"] = str((Decimal(mg["SB"]) / 2).quantize(Decimal("0.01")))
            info["bb"] = str(Decimal(mg["SB"]).quantize(Decimal("0.01")))

        return info

    def readHandInfo(self, hand) -> None:
        info = {}
        m = self.re_HandInfo.search(hand.handText)
        if m is None:
            tmp = hand.handText[:200]
            log.error(f"read Hand Info failed: '{tmp}'")
            raise FpdbParseError

        info |= m.groupdict()
        log.debug(f"read Hand Info: {info}")
        for key, value in info.items():
            if key == "DATETIME":
                if a := self.re_DateTime.search(value):
                    datetimestr = (
                        f"{a.group('Y')}/{a.group('M')}/{a.group('D')}"
                        f" {a.group('H')}:{a.group('MIN')}:{a.group('S')}"
                    )
                else:
                    datetimestr = "2010/Jan/01 01:01:01"
                    log.warning(f"DATETIME not matched: '{info[key]}'")
                hand.startTime = datetime.datetime.strptime(
                    datetimestr, "%Y/%m/%d %H:%M:%S",
                )
            elif key == "HID1":
                # Need to remove non-alphanumerics for MySQL
                # Concatenating all three or just HID2 + HID3 can produce out of range values
                # HID should not be greater than 14 characters to ensure this
                hand.handid = f"{int(info['HID1'][:14])}{int(info['HID2'])}"

            elif key == "TOURNO":
                hand.tourNo = info[key]
            if key == "TABLE":
                hand.tablename = info[key]
                if hand.gametype["type"] == "tour":
                    hand.tablename = info["TABLENO"]
                    hand.roundPenny = True
                # TODO: long-term solution for table naming on Winamax.
                if hand.tablename.endswith("No Limit Hold'em"):
                    hand.tablename = hand.tablename[: -len("No Limit Hold'em")] + "NLHE"
            if key == "MAXPLAYER" and info[key] is not None:
                hand.maxseats = int(info[key])

            if key == "BUYIN" and hand.tourNo is not None:
                log.debug(f"info['BUYIN']: {info['BUYIN']}")
                log.debug(f"info['BIAMT']: {info['BIAMT']}")
                log.debug(f"info['BIRAKE']: {info['BIRAKE']}")
                log.debug(f"info['BOUNTY']: {info['BOUNTY']}")
                for k in ["BIAMT", "BIRAKE"]:
                    if info.get(k):
                        info[k] = info[k].replace(",", ".")

                if info["FREETICKET"] is not None:
                    hand.buyin = 0
                    hand.fee = 0
                    hand.buyinCurrency = "FREE"
                else:
                    if info[key].find("$") != -1:
                        hand.buyinCurrency = "USD"
                    elif info[key].find("€") != -1:
                        hand.buyinCurrency = "EUR"
                    elif info[key].find("FPP") != -1 or info[key].find("Free") != -1:
                        hand.buyinCurrency = "WIFP"
                    elif info["MONEY"]:
                        hand.buyinCurrency = "EUR"
                    else:
                        hand.buyinCurrency = "play"

                    info["BIAMT"] = (
                        info["BIAMT"].strip("$€FPP") if info["BIAMT"] is not None else 0
                    )
                    if hand.buyinCurrency != "WIFP":
                        if info["BOUNTY"] is not None:
                            # There is a bounty, Which means we need to switch BOUNTY and BIRAKE values
                            tmp = info["BOUNTY"]
                            info["BOUNTY"] = info["BIRAKE"]
                            info["BIRAKE"] = tmp
                            info["BOUNTY"] = info["BOUNTY"].strip(
                                "$€",
                            )  # Strip here where it isn't 'None'
                            hand.koBounty = int(100 * Decimal(info["BOUNTY"]))
                            hand.isKO = True
                        else:
                            hand.isKO = False

                        info["BIRAKE"] = info["BIRAKE"].strip("$€")

                        # TODO: Is this correct? Old code tried to
                        # conditionally multiply by 100, but we
                        # want hand.buyin in 100ths of
                        # dollars/euros (so hand.buyin = 90 for $0.90 BI).
                        hand.buyin = int(100 * Decimal(info["BIAMT"]))
                        hand.fee = int(100 * Decimal(info["BIRAKE"]))
                    else:
                        hand.buyin = int(Decimal(info["BIAMT"]))
                        hand.fee = 0
                    if hand.buyin == 0 and hand.fee == 0:
                        hand.buyinCurrency = "FREE"

            if key == "LEVEL":
                hand.level = info[key]

        hand.mixed = None

    def readPlayerStacks(self, hand) -> None:
        # Split hand text for Winamax, as the players listed in the hh preamble and the summary will differ
        # if someone is sitting out.
        # Going to parse both and only add players in the summary.
        handsplit = hand.handText.split("*** SUMMARY ***")
        if len(handsplit) != 2:
            msg = f"Hand is not cleanly split into pre and post Summary {hand.handid}."
            raise FpdbHandPartial(
                msg,
            )
        pre, post = handsplit
        m = self.re_PlayerInfo.finditer(pre)
        plist = {}

        # Get list of players in header.
        for a in m:
            if plist.get(a.group("PNAME")) is None:
                hand.addPlayer(int(a.group("SEAT")), a.group("PNAME"), a.group("CASH"))
                plist[a.group("PNAME")] = [int(a.group("SEAT")), a.group("CASH")]

        if len(plist.keys()) < 2:
            msg = f"Less than 2 players in hand! {hand.handid}."
            raise FpdbHandPartial(msg)

    def markStreets(self, hand) -> None:
        if hand.gametype["base"] == "hold":
            m = re.search(
                r"\*\*\* ANTE/BLINDS \*\*\*(?P<PREFLOP>.+(?=\*\*\* FLOP \*\*\*)|.+)"
                r"(\*\*\* FLOP \*\*\*(?P<FLOP> \[\S\S \S\S \S\S\].+(?=\*\*\* TURN \*\*\*)|.+))?"
                r"(\*\*\* TURN \*\*\* \[\S\S \S\S \S\S](?P<TURN>\[\S\S\].+(?=\*\*\* RIVER \*\*\*)|.+))?"
                r"(\*\*\* RIVER \*\*\* \[\S\S \S\S \S\S \S\S](?P<RIVER>\[\S\S\].+))?",
                hand.handText,
                re.DOTALL,
            )
        elif hand.gametype["base"] == "stud":
            m = re.search(
                r"\*\*\* ANTE/BLINDS \*\*\*(?P<ANTES>.+(?=\*\*\* (3rd STREET|THIRD) \*\*\*)|.+)"
                r"(\*\*\* (3rd STREET|THIRD) \*\*\*(?P<THIRD>.+(?=\*\*\* (4th STREET|FOURTH) \*\*\*)|.+))?"
                r"(\*\*\* (4th STREET|FOURTH) \*\*\*(?P<FOURTH>.+(?=\*\*\* (5th STREET|FIFTH) \*\*\*)|.+))?"
                r"(\*\*\* (5th STREET|FIFTH) \*\*\*(?P<FIFTH>.+(?=\*\*\* (6th STREET|SIXTH) \*\*\*)|.+))?"
                r"(\*\*\* (6th STREET|SIXTH) \*\*\*(?P<SIXTH>.+(?=\*\*\* (7th STREET|SEVENTH) \*\*\*)|.+))?"
                r"(\*\*\* (7th STREET|SEVENTH) \*\*\*(?P<SEVENTH>.+))?",
                hand.handText,
                re.DOTALL,
            )
        else:
            m = re.search(
                r"\*\*\* ANTE/BLINDS \*\*\*(?P<PREDEAL>.+(?=\*\*\* FIRST\-BET \*\*\*)|.+)"
                r"(\*\*\* FIRST\-BET \*\*\*(?P<DEAL>.+(?=\*\*\* FIRST\-DRAW \*\*\*)|.+))?"
                r"(\*\*\* FIRST\-DRAW \*\*\*(?P<DRAWONE>.+(?=\*\*\* SECOND\-DRAW \*\*\*)|.+))?"
                r"(\*\*\* SECOND\-DRAW \*\*\*(?P<DRAWTWO>.+(?=\*\*\* THIRD\-DRAW \*\*\*)|.+))?"
                r"(\*\*\* THIRD\-DRAW \*\*\*(?P<DRAWTHREE>.+))?",
                hand.handText,
                re.DOTALL,
            )

        try:
            hand.addStreets(m)
            log.debug(f"adding street {m.group(0)}")
            log.debug("---")
        except Exception:
            log.info(f"Failed to add streets. handtext={hand.handtext}")

    # Needs to return a list in the format
    # ['player1name', 'player2name', ...] where player1name is the sb and player2name is bb,
    # addtional players are assumed to post a bb oop

    def readButton(self, hand) -> None:
        if m := self.re_Button.search(hand.handText):
            hand.buttonpos = int(m.group("BUTTON"))
            log.debug(f"read Button: button on pos {hand.buttonpos}")
        else:
            log.info("read Button: not found")

    #    def readCommunityCards(self, hand, street):
    #        #print hand.streets.group(street)
    #        if street in ('FLOP','TURN','RIVER'):
    # a list of streets which get dealt community cards (i.e. all but PREFLOP)
    #            m = self.re_Board.search(hand.streets.group(street))
    #            hand.setCommunityCards(street, m.group('CARDS').split(','))

    def readCommunityCards(
        self, hand, street,
    ) -> None:  # street has been matched by markStreets, so exists in this hand
        if street in ("FLOP", "TURN", "RIVER"):
            # a list of streets which get dealt community cards (i.e. all but PREFLOP)
            # print("DEBUG readCommunityCards:", street, hand.streets.group(street))
            m = self.re_Board.search(hand.streets[street])
            hand.setCommunityCards(street, m.group("CARDS").split(" "))

    def readBlinds(self, hand) -> None:
        # found_small, found_big = False, False

        m = self.re_PostSB.search(hand.handText)
        if m is not None:
            hand.addBlind(m.group("PNAME"), "small blind", m.group("SB"))
            # found_small = True
        else:
            log.debug("No small blind")
            hand.addBlind(None, None, None)

        for a in self.re_PostBB.finditer(hand.handText):
            hand.addBlind(a.group("PNAME"), "big blind", a.group("BB"))
            amount = Decimal(a.group("BB").replace(",", ""))
            hand.lastBet["PREFLOP"] = amount
        for a in self.re_PostDead.finditer(hand.handText):
            log.debug(
                f"Found dead blind: addBlind({a.group('PNAME')}, 'secondsb', {a.group('DEAD')})",
            )
            hand.addBlind(a.group("PNAME"), "secondsb", a.group("DEAD"))
        for a in self.re_PostSecondSB.finditer(hand.handText):
            log.debug(
                f"Found dead blind: addBlind({a.group('PNAME')}, 'secondsb/both', {a.group('SB')}, {hand.sb})",
            )
            if Decimal(a.group("SB")) > Decimal(hand.sb):
                hand.addBlind(a.group("PNAME"), "both", a.group("SB"))
            else:
                hand.addBlind(a.group("PNAME"), "secondsb", a.group("SB"))

    def readAntes(self, hand) -> None:
        log.debug("reading antes")
        m = self.re_Antes.finditer(hand.handText)
        for player in m:
            log.debug(f"hand add Ante({player.group('PNAME')},{player.group('ANTE')})")
            hand.addAnte(player.group("PNAME"), player.group("ANTE"))

    def readBringIn(self, hand) -> None:
        if m := self.re_BringIn.search(hand.handText, re.DOTALL):
            log.debug(f"read BringIn: {m.group('PNAME')} for {m.group('BRINGIN')}")
            hand.addBringIn(m.group("PNAME"), m.group("BRINGIN"))

    def readSTP(self, hand) -> None:
        if m := self.re_HUTP.search(hand.handText):
            hand.addSTP(m.group("AMOUNT"))

    def readHoleCards(self, hand) -> None:
        # streets PREFLOP, PREDRAW, and THIRD are special cases beacause
        # we need to grab hero's cards
        for street in ("PREFLOP", "DEAL", "BLINDSANTES"):
            if street in hand.streets:
                m = self.re_HeroCards.finditer(hand.streets[street])
                for found in m:
                    if newcards := [
                        c for c in found.group("NEWCARDS").split(" ") if c != "X"
                    ]:
                        hand.hero = found.group("PNAME")

                        log.debug(
                            f"DEBUG: {hand.handid} addHoleCards({street}, {hand.hero}, {newcards})",
                        )

                        hand.addHoleCards(
                            street,
                            hand.hero,
                            closed=newcards,
                            shown=False,
                            mucked=False,
                            dealt=True,
                        )
                        log.debug(f"Hero cards {hand.hero}: {newcards}")

        for street, text in list(hand.streets.items()):
            if not text or street in ("PREFLOP", "DEAL", "BLINDSANTES"):
                continue  # already done these
            m = self.re_HeroCards.finditer(hand.streets[street])
            for found in m:
                player = found.group("PNAME")
                if found.group("NEWCARDS") is None:
                    newcards = []
                else:
                    newcards = [
                        c for c in found.group("NEWCARDS").split(" ") if c != "X"
                    ]
                if found.group("OLDCARDS") is None:
                    oldcards = []
                else:
                    oldcards = [
                        c for c in found.group("OLDCARDS").split(" ") if c != "X"
                    ]

                if street == "THIRD" and len(newcards) == 3:  # hero in stud game
                    hand.hero = player
                    hand.dealt.add(player)  # need this for stud??
                    hand.addHoleCards(
                        street,
                        player,
                        closed=newcards[:2],
                        open=[newcards[2]],
                        shown=False,
                        mucked=False,
                        dealt=False,
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

    def readAction(self, hand, street) -> None:
        streetsplit = hand.streets[street].split("*** SUMMARY ***")
        m = self.re_Action.finditer(streetsplit[0])
        for action in m:
            acts = action.groupdict()
            log.debug(f"read actions: acts: {acts}")
            if action.group("ATYPE") == " folds":
                hand.addFold(street, action.group("PNAME"))
            elif action.group("ATYPE") == " checks":
                hand.addCheck(street, action.group("PNAME"))
            elif action.group("ATYPE") == " calls":
                hand.addCall(street, action.group("PNAME"), action.group("BET"))
            elif action.group("ATYPE") == " raises":
                if bringin := [
                    act[2]
                    for act in hand.actions[street]
                    if act[0] == action.group("PNAME") and act[1] == "bringin"
                ]:
                    betto = str(Decimal(action.group("BETTO")) + bringin[0])
                else:
                    betto = action.group("BETTO")
                hand.addRaiseTo(street, action.group("PNAME"), betto)
            elif action.group("ATYPE") == " bets":
                if street in ("PREFLOP", "DEAL", "THIRD", "BLINDSANTES"):
                    hand.addRaiseBy(street, action.group("PNAME"), action.group("BET"))
                else:
                    hand.addBet(street, action.group("PNAME"), action.group("BET"))
            elif action.group("ATYPE") == " discards":
                hand.addDiscard(
                    street,
                    action.group("PNAME"),
                    action.group("BET"),
                    action.group("DISCARDED"),
                )
            elif action.group("ATYPE") == " stands pat":
                hand.addStandsPat(street, action.group("PNAME"))
            else:
                log.error(
                    f"Unimplemented readAction: '{action.group('PNAME')}' '{action.group('ATYPE')}'",
                )
            log.debug(f"Processed {acts}")
            log.debug(f"committed {hand.pot.committed}")

    def readShowdownActions(self, hand) -> None:
        for shows in self.re_ShowdownAction.finditer(hand.handText):
            log.debug(f"add show actions {shows}")
            cards = shows.group("CARDS")
            cards = cards.split(" ")
            log.debug(f"add Shown Cards({cards}, {shows.group('PNAME')})")
            hand.addShownCards(cards, shows.group("PNAME"))

    def readCollectPot(self, hand) -> None:
        hand.setUncalledBets(True)
        for m in self.re_CollectPot.finditer(hand.handText):
            hand.addCollectPot(player=m.group("PNAME"), pot=m.group("POT"))

    def readShownCards(self, hand) -> None:
        for m in self.re_ShownCards.finditer(hand.handText):
            log.debug(f"Read shown cards: {m.group(0)}")
            cards = m.group("CARDS")
            cards = cards.split(
                " ",
            )  # needs to be a list, not a set--stud needs the order
            (shown, mucked) = (False, False)
            if m.group("CARDS") is not None:
                shown = True
                string = m.group("STRING")
                log.debug(f"{m.group('PNAME')} {cards} {shown} {mucked}")
                hand.addShownCards(
                    cards=cards,
                    player=m.group("PNAME"),
                    shown=shown,
                    mucked=mucked,
                    string=string,
                )

    def readSummaryInfo(self, summaryInfoList) -> bool:
        """Implement the abstract method from HandHistoryConverter."""
        # Add the actual implementation here, or use a placeholder if not needed
        log.info("Reading summary info for Winamax.")
        return True

    def readTourneyResults(self, hand) -> None:
        """Implement the abstract method from HandHistoryConverter."""
        # Add the actual implementation here, or use a placeholder if not needed
        log.info("Reading tournay result info for Winamax.")

    @staticmethod
    def getTableTitleRe(type, table_name=None, tournament=None, table_number=None):
        log.info(
            f"Winamax.getTableTitleRe: table_name='{table_name}' tournament='{tournament}' table_number='{table_number}'",
        )
        sysPlatform = platform.system()  # Linux, Windows, Darwin
        regex = f"Winamax {table_name}" if sysPlatform[:5] == "Linux" else f"Winamax {table_name} /"
        log.debug(f"regex get table cash title: {regex}")
        if tournament:
            regex = rf"Winamax\s+([^\(]+)\({tournament}\)\(#0*{table_number}\)"

            log.debug(f"regex get mtt sng expresso cash title: {regex}")
        log.info(f"Winamax.getTableTitleRe: returns: '{regex}'")
        return regex
