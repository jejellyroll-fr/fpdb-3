#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2008-2012 Chaz Littlejohn
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


# import L10n
# _ = L10n.get_translation()

from HandHistoryConverter import FpdbParseError
import re
import logging
import datetime
from TourneySummary import TourneySummary
from decimal import Decimal

# PokerStars HH Format
log = logging.getLogger("parser")


class PokerTrackerSummary(TourneySummary):
    hhtype = "summary"
    limits = {"NL": "nl", "No Limit": "nl", "Pot Limit": "pl", "PL": "pl", "FL": "fl", "Limit": "fl", "LIMIT": "fl"}
    games = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "Texas Hold'em": ("hold", "holdem"),
        "Holdem": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi": ("hold", "omahahi"),
        "Omaha Hi/Lo": ("hold", "omahahilo"),
    }

    substitutions = {
        "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP",  # legal ISO currency codes
        "LS": "\$|€|\£|P|SC|",  # legal currency symbols - Euro(cp1252, utf-8)
        "PLYR": r"(?P<PNAME>.+?)",
        "NUM": ".,\d",
        "CUR": "(\$|€||\£|)",
    }

    re_Identify = re.compile("PokerTracker")

    re_TourneyInfo = re.compile(
        """
                        \s(3|4)\sTournament\sSummary\s+
                        Site:\s(?P<SITE>.+?)\s+
                        Game:\s(?P<GAME>Holdem|Texas\sHold\'em|Omaha|Omaha\sHi|Omaha\sHi\/Lo)\s+
                        Tournament\s\#:\s(?P<TOURNO>[0-9]+)\s+
                        Started:\s(?P<DATETIME>.+?)\s+
                        Finished:\s(?P<DATETIME1>.+?)\s+
                        Buyin:\s(?P<CURRENCY>[%(LS)s]?)(?P<BUYIN>[,.0-9]+)\s+
                        (Bounty:\s[%(LS)s]?(?P<BOUNTY>[,.0-9]+)\s+)?
                        Fee:\s[%(LS)s]?(?P<FEE>[,.0-9]+)\s+
                        (Prize\sPool:\s[%(LS)s]?(?P<PRIZEPOOL>[,.0-9]+)\s+)?
                        (Rebuy:\s[%(LS)s]?(?P<REBUYAMT>[,.0-9]+)\s+)?
                        (Addon:\s[%(LS)s]?(?P<ADDON>[,.0-9]+)\s+)?
                        Initial\sStack:\s(?P<STACK>[0-9]+)\s+
                        Table\sType:\s(?P<TYPE>.+?)\s+
                        Tourney\sType:\s(?P<LIMIT>No\sLimit|Limit|LIMIT|Pot\sLimit|N\/A)\s+
                        Players:\s(?P<ENTRIES>\d+)\s+
                        """
        % substitutions,
        re.VERBOSE | re.MULTILINE,
    )

    re_Max = re.compile("\((?P<MAX>\d+)\smax\)\s")
    re_Speed = re.compile("(?P<SPEED>Turbo|Hyper\-Turbo)")
    re_Sng = re.compile("\s(?P<SNG>SNG)\s")

    re_Player = re.compile(
        """
        Place:\s(?P<RANK>[0-9]+),\s
        Player:\s(?P<NAME>.*),\s
        Won:\s(?P<CUR>[%(LS)s]?)(?P<WINNINGS>[,.0-9]+),
        (\sBounties:\s(?P<KOS>\d+),)?
        (\sRebuys:\s(?P<REBUYS>\d+),)?
        (\sAddons:\s(?P<ADDONS>\d+),)?
        """
        % substitutions,
        re.VERBOSE,
    )

    re_DateTime = re.compile(
        """(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""",
        re.MULTILINE,
    )

    codepage = ["utf-8", "cp1252"]

    siteNameMap = {
        "Pacific Poker": "PacificPoker",
        "MicroGaming": "Microgaming",
        "PokerStars": "PokerStars",
        "Full Tilt": "Fulltilt",
        "Party Poker": "PartyPoker",
        "Merge": "Merge",
        "Winamax": "Winamax",
    }

    @staticmethod
    def getSplitRe(self, head):
        re_SplitTourneys = re.compile("PokerTracker")
        return re_SplitTourneys

    def parseSummary(self):
        m = self.re_TourneyInfo.search(self.summaryText)
        if m is None:
            tmp = self.summaryText[0:200]
            log.error(("PokerTrackerSummary.parseSummary: '%s'") % tmp)
            raise FpdbParseError

        # print "DEBUG: m.groupdict(): %s" % m.groupdict()

        mg = m.groupdict()
        if "SITE" in mg:
            if self.siteNameMap.get(mg["SITE"]) is not None:
                self.siteName = self.siteNameMap.get(mg["SITE"])
                self.siteId = self.SITEIDS.get(self.siteName)
            else:
                tmp = self.summaryText[0:200]
                log.error(("PokerTrackerSummary.parseSummary: Unsupported site summary '%s'") % tmp)
                raise FpdbParseError
        if "TOURNO" in mg:
            self.tourNo = mg["TOURNO"]
        if "GAME" in mg:
            self.gametype["category"] = self.games[mg["GAME"]][1]
        if mg["LIMIT"] in self.limits:
            self.gametype["limitType"] = self.limits[mg["LIMIT"]]
        elif self.gametype["category"] == "holdem":
            self.gametype["limitType"] = "nl"
        else:
            self.gametype["limitType"] = "pl"
        if "TYPE" in mg:
            self.tourneyName = mg["TYPE"]
            t1 = self.re_Max.search(self.tourneyName)
            if t1:
                self.maxseats = int(t1.group("MAX"))
            t2 = self.re_Speed.search(self.tourneyName)
            if t2:
                if t2.group("SPEED") == "Turbo":
                    self.speed = "Turbo"
                elif t2.group("SPEED") == "Hyper-Turbo":
                    self.speed = "Hyper"
            t3 = self.re_Sng.search(self.tourneyName)
            if t3:
                self.isSng = True
            if "DEEP" in self.tourneyName:
                self.stack = "Deep"
            if "SATELLITE" in self.tourneyName:
                self.isSatellite = True
        if mg["BUYIN"] is not None:
            self.buyin = int(100 * float(self.clearMoneyString(mg["BUYIN"])))
        if mg["FEE"] is not None:
            self.fee = int(100 * float(self.clearMoneyString(mg["FEE"])))
        if "REBUYAMT" in mg and mg["REBUYAMT"] is not None:
            self.isRebuy = True
            self.rebuyCost = int(100 * float(self.clearMoneyString(mg["REBUYAMT"])))
        if "PRIZEPOOL" in mg and mg["PRIZEPOOL"] is not None:
            self.prizepool = int(100 * float(self.clearMoneyString(mg["PRIZEPOOL"])))
        if "ADDON" in mg and mg["ADDON"] is not None:
            self.isAddOn = True
            self.addOnCost = int(100 * float(self.clearMoneyString(mg["ADDON"])))
        if "BOUNTY" in mg and mg["BOUNTY"] is not None:
            self.koBounty = int(100 * float(self.clearMoneyString(mg["BOUNTY"])))
            self.isKO = True
        if "ENTRIES" in mg:
            self.entries = mg["ENTRIES"]
        if "DATETIME" in mg:
            m1 = self.re_DateTime.finditer(mg["DATETIME"])
            for a in m1:
                datetimestr = "%s/%s/%s %s:%s:%s" % (
                    a.group("Y"),
                    a.group("M"),
                    a.group("D"),
                    a.group("H"),
                    a.group("MIN"),
                    a.group("S"),
                )
        else:
            datetimestr = "2000/01/01 00:00:00"  # default used if time not found

        self.startTime = datetime.datetime.strptime(
            datetimestr, "%Y/%m/%d %H:%M:%S"
        )  # also timezone at end, e.g. " ET"

        if mg["CURRENCY"] == "$":
            self.buyinCurrency = "USD"
        elif mg["CURRENCY"] == "€":
            self.buyinCurrency = "EUR"
        elif mg["CURRENCY"] in ("SC", "P"):
            self.buyinCurrency = "PSFP"
        elif not mg["CURRENCY"]:
            self.buyinCurrency = "play"
        if self.buyin == 0:
            self.buyinCurrency = "FREE"
        self.currency = self.buyinCurrency

        if self.buyinCurrency not in ("FREE", "PSFP") and "ENTRIES" in mg and self.prizepool == 0:
            self.prizepool = int(Decimal(self.clearMoneyString(mg["BUYIN"]))) * int(self.entries)

        m = self.re_Player.finditer(self.summaryText)
        for a in m:
            mg = a.groupdict()
            # print "DEBUG: a.groupdict(): %s" % mg
            name = mg["NAME"]
            rank = int(mg["RANK"])
            winnings = 0
            rebuyCount = None
            addOnCount = None
            koCount = None
            if len(name) > 0:
                if "WINNINGS" in mg and mg["WINNINGS"] is not None:
                    # winning1 = mg["WINNINGS"]
                    # winning2 = self.clearMoneyString(winning1)
                    # winning3 = int(float(winning2))
                    winnings = int(100 * float(self.clearMoneyString(mg["WINNINGS"])))

                if "REBUYS" in mg and mg["REBUYS"] is not None:
                    rebuyCount = int(mg["REBUYS"])

                if "ADDONS" in mg and mg["ADDONS"] is not None:
                    addOnCount = int(mg["ADDONS"])

                if "KOS" in mg and mg["KOS"] is not None:
                    koCount = int(mg["KOS"])

                if "CUR" in mg and mg["CUR"] is not None:
                    if mg["CUR"] == "$":
                        self.currency = "USD"
                    elif mg["CUR"] == "€":
                        self.currency = "EUR"
                    elif mg["CUR"] in ("P", "SC"):
                        self.currency = "PSFP"

                if rank == 0:
                    # print "stillplaying"
                    rank = None
                    winnings = None

                if len(name) == 0:
                    log.debug("DEBUG: a.groupdict(): %s" % (mg))

                # print "DEBUG: addPlayer(%s, %s, %s, %s, None, None, None)" %(rank, name, winnings, self.currency)
                # print "DEBUG: self.buyin: %s self.fee %s" %(self.buyin, self.fee)
                self.addPlayer(rank, name, winnings, self.currency, rebuyCount, addOnCount, koCount)

        # print self


# end class PokerStarsSummary
