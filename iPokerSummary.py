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

# import L10n
# _ = L10n.get_translation()
from HandHistoryConverter import FpdbParseError, FpdbHandPartial
from decimal import Decimal
import re
import logging
import datetime
from TourneySummary import TourneySummary

log = logging.getLogger("parser")


class iPokerSummary(TourneySummary):
    substitutions = {
        "LS": "\$|\xe2\x82\xac|\xe2\u201a\xac|\u20ac|\xc2\xa3|\£|RSD|kr|",
        "PLYR": r'(?P<PNAME>[^"]+)',
        "NUM": r".,0-9",
        "NUM2": r"\b((?:\d{1,3}(?:\s\d{3})*)|(?:\d+))\b",  # Regex pattern for matching numbers with spaces
    }
    currencies = {"€": "EUR", "$": "USD", "": "T$", "£": "GBP", "RSD": "RSD", "kr": "SEK"}

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
        "LZ": "fl",
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
    }

    re_Identify = re.compile("<game\sgamecode=")
    re_client = re.compile(r"<client_version>(?P<CLIENT>.*?)</client_version>")
    re_GameType = re.compile(
        r"""
            <gametype>(?P<GAME>((?P<CATEGORY>(5|7)\sCard\sStud(\sHi\-Lo)?(\sHiLow)?|(Six\sPlus\s)?Holdem|Omaha(\sHi\-Lo)?(\sHiLow)?)?\s?(?P<LIMIT>NL|SL|L|LZ|PL|БЛ|LP|No\slimit|Pot\slimit|Limit))|LH\s(?P<LSB>[%(NUM)s]+)(%(LS)s)?/(?P<LBB>[%(NUM)s]+)(%(LS)s)?.+?)
            (\s(%(LS)s)?(?P<SB>[%(NUM)s]+)(%(LS)s)?/(%(LS)s)?(?P<BB>[%(NUM)s]+))?(%(LS)s)?(\sAnte\s(%(LS)s)?(?P<ANTE>[%(NUM)s]+)(%(LS)s)?)?</gametype>\s+?
            <tablename>(?P<TABLE>.+)?</tablename>\s+?
            (<(tablecurrency|tournamentcurrency)>.*</(tablecurrency|tournamentcurrency)>\s+?)?
            (<smallblind>.+</smallblind>\s+?)?
            (<bigblind>.+</bigblind>\s+?)?
            <duration>.+</duration>\s+?
            <gamecount>.+</gamecount>\s+?
            <startdate>(?P<DATETIME>.+)</startdate>\s+?
            <currency>(?P<CURRENCY>.+)</currency>\s+?
            <nickname>(?P<HERO>.+)</nickname>
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
                    (?:(<win>(%(LS)s)?(?P<WIN>[%(NUM2)s%(LS)s]+)</win>))
                    """
        % substitutions,
        re.VERBOSE,
    )
    re_GameInfoTrny2 = re.compile(
        r"""
                        (?:(<tour(?:nament)?code>(?P<TOURNO>\d+)</tour(?:nament)?code>))|
                        (?:(<tournamentname>(?P<NAME>[^<]*)</tournamentname>))|
                        (?:(<place>(?P<PLACE>.+?)</place>))|
                        (?:(<buyin>(?P<BIAMT>[%(NUM2)s%(LS)s]+)\s\+\s)?(?P<BIRAKE>[%(NUM2)s%(LS)s]+)</buyin>)|
                        (?:(<totalbuyin>(?P<TOTBUYIN>[%(NUM2)s%(LS)s]+)</totalbuyin>))|
                        (?:(<win>(%(LS)s)?(?P<WIN>.+?|[%(NUM2)s%(LS)s]+)</win>))
                        """
        % substitutions,
        re.VERBOSE,
    )
    re_Buyin = re.compile(r"""(?P<BUYIN>[%(NUM)s]+)""" % substitutions, re.MULTILINE | re.VERBOSE)
    re_TourNo = re.compile(r"(?P<TOURNO>\d+)$", re.MULTILINE)
    re_TotalBuyin = re.compile(
        r"""(?P<BUYIN>(?P<BIAMT>[%(LS)s%(NUM)s]+)\s\+\s?(?P<BIRAKE>[%(LS)s%(NUM)s]+)?)""" % substitutions,
        re.MULTILINE | re.VERBOSE,
    )
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
    re_Place = re.compile(r"""(?:(<place>(?P<PLACE>.+?)</place>))""" % substitutions, re.VERBOSE)
    re_FPP = re.compile(r"Pts\s")

    codepage = ["utf8", "cp1252"]

    @staticmethod
    def getSplitRe(self, head):
        re_SplitTourneys = re.compile("PokerStars Tournament ")
        return re_SplitTourneys

    def parseSummary(self):
        m = self.re_GameType.search(self.summaryText)
        if not m:
            tmp = self.summaryText[0:200]
            log.error(("iPokerSummary.determineGameType: '%s'") % tmp)
            raise FpdbParseError

        mg = m.groupdict()
        # print "DEBUG: m.groupdict(): %s" % mg

        if "SB" in mg and mg["SB"] is not None:
            tmp = self.summaryText[0:200]
            log.error(("iPokerSummary.parseSummary: Text does not appear to be a tournament '%s'") % tmp)
            raise FpdbParseError
        else:
            tourney = True
        #                self.gametype['limitType'] =
        if "GAME" in mg:
            if mg["CATEGORY"] is None:
                (self.info["base"], self.info["category"]) = ("hold", "5_omahahi")
            else:
                (self.gametype["base"], self.gametype["category"]) = self.games[mg["CATEGORY"]]
        if "LIMIT" in mg:
            self.gametype["limitType"] = self.limits[mg["LIMIT"]]

        m2 = self.re_DateTime1.search(mg["DATETIME"])
        if m2:
            month = self.months[m2.group("M")]
            sec = m2.group("S")
            if m2.group("S") is None:
                sec = "00"
            datetimestr = "%s/%s/%s %s:%s:%s" % (
                m2.group("Y"),
                month,
                m2.group("D"),
                m2.group("H"),
                m2.group("MIN"),
                sec,
            )
            self.startTime = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S")
        else:
            try:
                self.startTime = datetime.datetime.strptime(mg["DATETIME"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                date_match = self.re_DateTime2.search(mg["DATETIME"])
                if date_match is not None:
                    datestr = "%d/%m/%Y %H:%M:%S" if "/" in mg["DATETIME"] else "%d.%m.%Y %H:%M:%S"
                    if date_match.group("S") is None:
                        datestr = "%d/%m/%Y %H:%M"
                else:
                    date_match1 = self.re_DateTime3.search(mg["DATETIME"])
                    datestr = "%Y/%m/%d %H:%M:%S"
                    if date_match1 is None:
                        log.error(("iPokerSummary.parseSummary Could not read datetime"))
                        raise FpdbParseError
                    if date_match1.group("S") is None:
                        datestr = "%Y/%m/%d %H:%M"
                self.startTime = datetime.datetime.strptime(mg["DATETIME"], datestr)

        if not mg["CURRENCY"] or mg["CURRENCY"] == "fun":
            self.buyinCurrency = "play"
        else:
            self.buyinCurrency = mg["CURRENCY"]
        self.currency = self.buyinCurrency

        mt = self.re_TourNo.search(mg["TABLE"])
        if mt:
            self.tourNo = mt.group("TOURNO")
        else:
            tourNo = mg["TABLE"].split(",")[-1].strip().split(" ")[0]
            if tourNo.isdigit():
                self.tourNo = tourNo

        if tourney:
            re_client_split = ".".join(self.re_client.split(".")[:2])
            if re_client_split == "23.5":  # betclic fr
                matches = list(self.re_GameInfoTrny.finditer(self.summaryText))
                if len(matches) > 0:
                    mg2 = {
                        "TOURNO": None,
                        "NAME": None,
                        "REWARD": None,
                        "PLACE": None,
                        "BIAMT": None,
                        "BIRAKE": None,
                        "BIRAKE2": None,
                        "TOTBUYIN": None,
                        "WIN": None,
                    }
                    mg2["TOURNO"] = matches[0].group("TOURNO")
                    mg2["NAME"] = matches[1].group("NAME")
                    mg2["REWARD"] = matches[2].group("REWARD")
                    mg2["PLACE"] = matches[3].group("PLACE")
                    mg2["BIAMT"] = matches[4].group("BIAMT")
                    mg2["BIRAKE"] = matches[4].group("BIRAKE")
                    mg2["BIRAKE2"] = matches[4].group("BIRAKE2")
                    mg2["TOTBUYIN"] = matches[5].group("TOTBUYIN")
                    mg2["WIN"] = matches[6].group("WIN")

                    self.buyin = 0
                    self.fee = 0
                    self.prizepool = None
                    self.entries = None

                    if mg2["TOURNO"]:
                        self.tourNo = mg2["TOURNO"]
                    # if mg2['CURRENCY']:
                    # self.currency = self.currencies[mg2['CURRENCY']]
                    rank, winnings = None, None
                    if "PLACE" in mg2 and self.re_Place.search(mg2["PLACE"]):
                        rank = int(mg2["PLACE"])
                        winnings = int(100 * self.convert_to_decimal(mg2["WIN"]))

                    self.tourneyName = mg2["NAME"].replace(" " + self.tourNo, "")

                    if not mg2["BIRAKE"] and mg2["TOTBUYIN"]:
                        m3 = self.re_TotalBuyin.search(mg2["TOTBUYIN"])
                        if m3:
                            mg2 = m3.groupdict()
                        elif mg2["BIAMT"]:
                            mg2["BIRAKE"] = "0"
                    if mg2["BIAMT"] and mg2["BIRAKE"]:
                        self.buyin = int(100 * self.convert_to_decimal(mg2["BIAMT"]))
                        self.fee = int(100 * self.convert_to_decimal(mg2["BIRAKE"]))
                        if "BIRAKE1" in mg2 and mg2["BIRAKE1"]:
                            self.buyin += int(100 * self.convert_to_decimal(mg2["BIRAKE1"]))
                        if self.re_FPP.match(mg2["BIAMT"]):
                            self.buyinCurrency = "FPP"
                    else:
                        self.buyin = 0
                        self.fee = 0
                    if self.buyin == 0:
                        self.buyinCurrency = "FREE"
                    hero = mg["HERO"]
                    self.addPlayer(rank, hero, winnings, self.currency, None, None, None)
                else:
                    raise FpdbHandPartial(hid=self.tourNo)
                if self.tourNo is None:
                    log.error(("iPokerSummary.parseSummary: Could Not Parse tourNo"))
                    raise FpdbParseError

            else:
                matches = list(self.re_GameInfoTrny2.finditer(self.summaryText))
                if len(matches) > 0:
                    mg2 = {
                        "TOURNO": None,
                        "NAME": None,
                        "PLACE": None,
                        "BIAMT": None,
                        "BIRAKE": None,
                        "TOTBUYIN": None,
                        "WIN": None,
                    }
                    mg2["TOURNO"] = matches[0].group("TOURNO")
                    mg2["NAME"] = matches[1].group("NAME")
                    mg2["PLACE"] = matches[2].group("PLACE")
                    mg2["BIAMT"] = matches[3].group("BIAMT")
                    mg2["BIRAKE"] = matches[3].group("BIRAKE")
                    mg2["TOTBUYIN"] = matches[4].group("TOTBUYIN")
                    mg2["WIN"] = matches[5].group("WIN")

                    self.buyin = 0
                    self.fee = 0
                    self.prizepool = None
                    self.entries = None

                    if mg2["TOURNO"]:
                        self.tourNo = mg2["TOURNO"]
                    # if mg2['CURRENCY']:
                    # self.currency = self.currencies[mg2['CURRENCY']]
                    rank, winnings = None, None
                    if "PLACE" in mg2 and mg2["PLACE"] != "N/A":
                        rank = int(mg2["PLACE"])
                        if mg2["WIN"] and mg2["WIN"] != "N/A":
                            winnings = int(100 * self.convert_to_decimal(mg2["WIN"]))

                    self.tourneyName = mg2["NAME"].replace(" " + self.tourNo, "")

                    if not mg2["BIRAKE"] and mg2["TOTBUYIN"]:
                        m3 = self.re_TotalBuyin.search(mg2["TOTBUYIN"])
                        if m3:
                            mg2 = m3.groupdict()
                        elif mg2["BIAMT"]:
                            mg2["BIRAKE"] = "0"
                    if mg2["BIAMT"] and mg2["BIRAKE"]:
                        self.buyin = int(100 * self.convert_to_decimal(mg2["BIAMT"]))
                        self.fee = int(100 * self.convert_to_decimal(mg2["BIRAKE"]))
                        if "BIRAKE1" in mg2 and mg2["BIRAKE1"]:
                            self.buyin += int(100 * self.convert_to_decimal(mg2["BIRAKE1"]))
                        if self.re_FPP.match(mg2["BIAMT"]):
                            self.buyinCurrency = "FPP"
                    else:
                        self.buyin = 0
                        self.fee = 0
                    if self.buyin == 0:
                        self.buyinCurrency = "FREE"
                    hero = mg["HERO"]
                    self.addPlayer(rank, hero, winnings, self.currency, None, None, None)
                else:
                    raise FpdbHandPartial(hid=self.tourNo)
                if self.tourNo is None:
                    log.error(("iPokerSummary.parseSummary: Could Not Parse tourNo"))
                    raise FpdbParseError
        else:
            tmp = self.summaryText[0:200]
            log.error(("iPokerSummary.determineGameType: Text does not appear to be a tournament '%s'") % tmp)
            raise FpdbParseError

    def convert_to_decimal(self, string):
        dec = self.clearMoneyString(string)
        m = self.re_Buyin.search(dec)
        if m:
            dec = Decimal(m.group("BUYIN"))
        else:
            dec = 0
        return dec
