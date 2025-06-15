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
from HandHistoryConverter import FpdbParseError
from decimal import Decimal
import re
from loggingFpdb import get_logger
import datetime
from TourneySummary import TourneySummary

log = get_logger("parser")


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
    games = {
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

    re_GameInfoTrny2 = re.compile(
        r"""
                        (?:(<tour(?:nament)?code>(?P<TOURNO>\d+)</tour(?:nament)?code>))|
                        (?:(<tournamentname>(?P<NAME>[^<]*)</tournamentname>))|
                        (?:(<place>(?P<PLACE>.+?)</place>))|
                        (?:(<buyin>(?P<BIAMT>[%(NUM2)s%(LS)s]+|\bToken\b)(?:\s\+\s)?(?P<BIRAKE>[%(NUM2)s%(LS)s]+)?)</buyin>)|
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
    re_Place = re.compile(r"""(<place>(?P<PLACE>.+?)</place>)""" % substitutions, re.VERBOSE)
    re_FPP = re.compile(r"Pts\s")

    # Add the non-decimal regex used to strip currency symbols/spaces:
    re_non_decimal = re.compile(r"[^\d.,]+")

    codepage = ["utf8", "cp1252"]

    @staticmethod
    def getSplitRe(self, head):
        re_SplitTourneys = re.compile("PokerStars Tournament ")
        return re_SplitTourneys

    def parseSummary(self):
        log.debug("Starting parseSummary.")
        m = self.re_GameType.search(self.summaryText)
        if not m:
            tmp = self.summaryText[0:200]
            log.error(f"determine GameType not found: '{tmp}'")
            raise FpdbParseError
        else:
            log.debug("Found a match for GameType.")

        mg = m.groupdict()
        log.debug(f"GameType match groups: {mg}")

        if "SB" in mg and mg["SB"] is not None:
            tmp = self.summaryText[0:200]
            log.error(f"Text does not appear to be a tournament: '{tmp}'")
            raise FpdbParseError
        else:
            log.debug("No SB found, treating as tournament.")
            tourney = True

        if "GAME" in mg:
            if mg.get("CATEGORY") is None:
                self.info["base"], self.info["category"] = ("hold", "5_omahahi")
                log.debug("No CATEGORY found, defaulting to hold/5_omahahi.")
            else:
                self.gametype["base"], self.gametype["category"] = self.games[mg["CATEGORY"]]
                log.debug(f"Set base/category to: {self.gametype['base']}/{self.gametype['category']}")

        if "LIMIT" in mg:
            self.gametype["limitType"] = self.limits[mg["LIMIT"]]
            log.debug(f"Set limitType to {self.gametype['limitType']}")

        m2 = self.re_DateTime1.search(mg["DATETIME"])
        if m2:
            month = self.months[m2.group("M")]
            sec = m2.group("S") or "00"
            datetimestr = f"{m2.group('Y')}/{month}/{m2.group('D')} {m2.group('H')}:{m2.group('MIN')}:{sec}"
            self.startTime = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S")
            log.debug(f"Parsed startTime with re_DateTime1: {self.startTime}")
        else:
            try:
                self.startTime = datetime.datetime.strptime(mg["DATETIME"], "%Y-%m-%d %H:%M:%S")
                log.debug(f"Parsed startTime with default format: {self.startTime}")
            except ValueError:
                log.debug("Default format failed, trying alternative date formats.")
                date_match = self.re_DateTime2.search(mg["DATETIME"])
                if date_match is not None:
                    datestr = "%d/%m/%Y %H:%M:%S" if "/" in mg["DATETIME"] else "%d.%m.%Y %H:%M:%S"
                    if date_match.group("S") is None:
                        datestr = "%d/%m/%Y %H:%M"
                else:
                    date_match1 = self.re_DateTime3.search(mg["DATETIME"])
                    if date_match1 is None:
                        log.error("Could not read datetime from the provided formats.")
                        raise FpdbParseError
                    datestr = "%Y/%m/%d %H:%M:%S"
                    if date_match1.group("S") is None:
                        datestr = "%Y/%m/%d %H:%M"
                self.startTime = datetime.datetime.strptime(mg["DATETIME"], datestr)
                log.debug(f"Parsed startTime with fallback format: {self.startTime}")

        if not mg["CURRENCY"] or mg["CURRENCY"] == "fun":
            self.buyinCurrency = "play"
            log.debug("Currency is fun/play, setting buyinCurrency=play")
        else:
            self.buyinCurrency = mg["CURRENCY"]
            log.debug(f"Set buyinCurrency to {self.buyinCurrency}")
        self.currency = self.buyinCurrency

        mt = self.re_TourNo.search(mg["TABLE"])
        if mt:
            self.tourNo = mt.group("TOURNO")
            log.debug(f"Extracted tourNo: {self.tourNo}")
        else:
            tourNo = mg["TABLE"].split(",")[-1].strip().split(" ")[0]
            if tourNo.isdigit():
                self.tourNo = tourNo
                log.debug(f"Parsed tourNo from table string: {self.tourNo}")
            else:
                log.debug("No numeric tourNo found in table string. TourNo may remain None.")

        if tourney:
            log.debug("Processing tournament-specific logic using re_GameInfoTrny2.")
            matches = list(self.re_GameInfoTrny2.finditer(self.summaryText))
            log.debug(f"Number of matches found with re_GameInfoTrny2: {len(matches)}")

            # Expecting at least 6 matches: 0=TOURNO, 1=NAME, 2=PLACE, 3=BIAMT/BIRAKE, 4=TOTBUYIN, 5=WIN
            if len(matches) < 6:
                log.error(f"Not enough matches for tournament info: found {len(matches)}, need at least 6.")
                log.debug(f"Summary text snippet for debugging:\n{self.summaryText[:500]}")
                raise FpdbParseError("Not enough matches for tournament info.")

            for i, mat in enumerate(matches):
                log.debug(f"Match {i}: {mat.groupdict()}")

            mg2 = {
                "TOURNO": matches[0].group("TOURNO"),
                "NAME": matches[1].group("NAME"),
                "PLACE": matches[2].group("PLACE"),
                "BIAMT": matches[3].group("BIAMT"),
                "BIRAKE": matches[3].group("BIRAKE"),
                "TOTBUYIN": matches[4].group("TOTBUYIN"),
                "WIN": matches[5].group("WIN"),
            }
            log.debug(f"Consolidated mg2: {mg2}")

            self.buyin = 0
            self.fee = 0
            self.prizepool = None
            self.entries = None

            if mg2["TOURNO"]:
                self.tourNo = mg2["TOURNO"]
                log.debug(f"Confirmed tourNo: {self.tourNo}")

            rank, winnings = None, None
            if mg2["PLACE"] and mg2["PLACE"] != "N/A":
                rank = int(mg2["PLACE"])
                log.debug(f"Extracted rank: {rank}")
                if mg2["WIN"] and mg2["WIN"] != "N/A":
                    winnings = int(100 * self.convert_to_decimal(mg2["WIN"]))
                    log.debug(f"Calculated winnings: {winnings}")

            self.tourneyName = mg2["NAME"]
            if self.tourNo and (" " + self.tourNo) in mg2["NAME"]:
                self.tourneyName = mg2["NAME"].replace(" " + self.tourNo, "")
            log.debug(f"Set tourneyName to {self.tourneyName}")

            # Handle "Token" buyin scenario
            if mg2["BIAMT"] and mg2["BIAMT"].strip().lower() == "token":
                log.debug("Buy-in detected as Token. Attempting fallback to TOTBUYIN.")
                if mg2["TOTBUYIN"]:
                    stripped_tot = self.re_non_decimal.sub("", mg2["TOTBUYIN"])
                    if stripped_tot:
                        mg2["BIAMT"] = stripped_tot
                        mg2["BIRAKE"] = "0"
                        log.debug(f"Converted Token buy-in: BIAMT={mg2['BIAMT']} and set BIRAKE=0.")
                    else:
                        log.debug("TOTBUYIN present but could not parse numeric value. Setting BIAMT=0.")
                        mg2["BIAMT"] = "0"
                        mg2["BIRAKE"] = "0"
                else:
                    log.debug("Token buyin but no TOTBUYIN available. Setting default buyin=0, fee=0.")
                    mg2["BIAMT"] = "0"
                    mg2["BIRAKE"] = "0"

            if not mg2["BIRAKE"] and mg2["TOTBUYIN"]:
                log.debug("No BIRAKE found, trying to parse TOTBUYIN.")
                m3 = self.re_TotalBuyin.search(mg2["TOTBUYIN"])
                if m3:
                    mg2.update(m3.groupdict())
                    log.debug(f"Updated mg2 with total buyin info: {mg2}")
                elif mg2.get("BIAMT"):
                    mg2["BIRAKE"] = "0"
                    log.debug("Set BIRAKE=0 due to missing explicit rake info, but BIAMT is present.")

            if mg2.get("BIAMT") and mg2.get("BIRAKE"):
                try:
                    self.buyin = int(100 * self.convert_to_decimal(mg2["BIAMT"]))
                except Exception:
                    log.debug(f"Failed to parse BIAMT='{mg2['BIAMT']}', setting buyin=0.")
                    self.buyin = 0
                try:
                    self.fee = int(100 * self.convert_to_decimal(mg2["BIRAKE"]))
                except Exception:
                    log.debug(f"Failed to parse BIRAKE='{mg2['BIRAKE']}', setting fee=0.")
                    self.fee = 0
                log.debug(f"Set buyin={self.buyin}, fee={self.fee}")

                if self.re_FPP.match(mg2["BIAMT"]):
                    self.buyinCurrency = "FPP"
                    log.debug("Detected FPP buyin currency.")
            else:
                log.debug("No valid BIAMT/BIRAKE info, setting buyin=0 and fee=0.")
                self.buyin = 0
                self.fee = 0

            if self.buyin == 0:
                self.buyinCurrency = "FREE"
                log.debug("No buyin found, setting buyinCurrency=FREE")

            hero = mg["HERO"]
            self.addPlayer(rank, hero, winnings, self.currency, None, None, None)
            log.debug(f"Added hero player: {hero}, rank={rank}, winnings={winnings}")

            if self.tourNo is None:
                log.error("Could Not Parse tourNo")
                raise FpdbParseError("Could Not Parse tourNo")

        else:
            tmp = self.summaryText[0:200]
            log.error(f"Text does not appear to be a tournament '{tmp}'")
            raise FpdbParseError

        log.debug("Finished parseSummary successfully.")

    def convert_to_decimal(self, string):
        dec = self.clearMoneyString(string)
        log.debug(f"Attempting to convert string to decimal: '{string}' => '{dec}'")
        if not dec:
            log.debug("Empty string after cleaning, returning 0.")
            return 0
        m = self.re_Buyin.search(dec)
        if m:
            try:
                dec = Decimal(m.group("BUYIN"))
                log.debug(f"Converted string '{string}' to decimal {dec}")
            except Exception as e:
                log.debug(f"Failed to convert '{string}' to decimal: {e}, defaulting to 0.")
                dec = 0
        else:
            log.debug(f"No numeric buyin match found in string '{string}', defaulting to 0.")
            dec = 0
        return dec
