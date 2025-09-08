"""PokerTracker tournament summary parser.

Copyright 2008-2012 Chaz Littlejohn
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
In the "official" distribution you can find the license in agpl-3.0.txt.
"""

import datetime
import re
from decimal import Decimal
from typing import ClassVar

from HandHistoryConverter import FpdbParseError
from loggingFpdb import get_logger
from TourneySummary import TourneySummary

# PokerTracker HH Format
log = get_logger("pokertracker_summary_parser")


class PokerTrackerSummary(TourneySummary):
    """PokerTracker tournament summary parser."""

    hhtype: ClassVar = "summary"
    limits: ClassVar = {
        "NL": "nl",
        "No Limit": "nl",
        "Pot Limit": "pl",
        "PL": "pl",
        "FL": "fl",
        "Limit": "fl",
        "LIMIT": "fl",
    }
    games: ClassVar = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "Texas Hold'em": ("hold", "holdem"),
        "Holdem": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi": ("hold", "omahahi"),
        "Omaha Hi/Lo": ("hold", "omahahilo"),
    }

    substitutions: ClassVar = {
        "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP",  # legal ISO currency codes
        "LS": r"\$|€|\£|P|SC|",  # legal currency symbols - Euro(cp1252, utf-8)
        "PLYR": r"(?P<PNAME>.+?)",
        "NUM": r".,\d",
        "CUR": r"(\$|€||\£|)",
    }

    re_identify = re.compile("PokerTracker")

    re_tourney_info = re.compile(
        """
                        \\s(3|4)\\sTournament\\sSummary\\s+
                        Site:\\s(?P<SITE>.+?)\\s+
                        Game:\\s(?P<GAME>Holdem|Texas\\sHold\'em|Omaha|Omaha\\sHi|Omaha\\sHi\\/Lo)\\s+
                        Tournament\\s\\#:\\s(?P<TOURNO>[0-9]+)\\s+
                        Started:\\s(?P<DATETIME>.+?)\\s+
                        Finished:\\s(?P<DATETIME1>.+?)\\s+
                        Buyin:\\s(?P<CURRENCY>[{LS}]?)(?P<BUYIN>[,.0-9]+)\\s+
                        (Bounty:\\s[{LS}]?(?P<BOUNTY>[,.0-9]+)\\s+)?
                        Fee:\\s[{LS}]?(?P<FEE>[,.0-9]+)\\s+
                        (Prize\\sPool:\\s[{LS}]?(?P<PRIZEPOOL>[,.0-9]+)\\s+)?
                        (Rebuy:\\s[{LS}]?(?P<REBUYAMT>[,.0-9]+)\\s+)?
                        (Addon:\\s[{LS}]?(?P<ADDON>[,.0-9]+)\\s+)?
                        Initial\\sStack:\\s(?P<STACK>[0-9]+)\\s+
                        Table\\sType:\\s(?P<TYPE>.+?)\\s+
                        Tourney\\sType:\\s(?P<LIMIT>No\\sLimit|Limit|LIMIT|Pot\\sLimit|N\\/A)\\s+
                        Players:\\s(?P<ENTRIES>\\d+)\\s+
                        """.format(**substitutions),
        re.VERBOSE | re.MULTILINE,
    )

    re_max = re.compile(r"\((?P<MAX>\d+)\smax\)\s")
    re_speed = re.compile(r"(?P<SPEED>Turbo|Hyper\-Turbo)")
    re_sng = re.compile(r"\s(?P<SNG>SNG)\s")

    re_player = re.compile(
        r"""
        Place:\s(?P<RANK>[0-9]+),\s
        Player:\s(?P<NAME>.*),\s
        Won:\s(?P<CUR>[{LS}]?)(?P<WINNINGS>[,.0-9]+),
        (\sBounties:\s(?P<KOS>\d+),)?
        (\sRebuys:\s(?P<REBUYS>\d+),)?
        (\sAddons:\s(?P<ADDONS>\d+),)?
        """.format(**substitutions),
        re.VERBOSE,
    )

    re_date_time = re.compile(
        r"""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""",
        re.MULTILINE,
    )

    codepage: ClassVar = ["utf-8", "cp1252"]

    site_name_map: ClassVar = {
        "Pacific Poker": "PacificPoker",
        "MicroGaming": "Microgaming",
        "PokerStars": "PokerStars",
        "Full Tilt": "Fulltilt",
        "Party Poker": "PartyPoker",
        "Merge": "Merge",
        "Winamax": "Winamax",
    }

    @staticmethod
    def getSplitRe(_head: str) -> re.Pattern[str]:
        """Get regex pattern for splitting tournament summaries."""
        return re.compile("PokerTracker")

    def parseSummary(self) -> None:  # noqa: PLR0912, PLR0915, C901
        """Parse tournament summary text."""
        m = self.re_tourney_info.search(self.summaryText)
        if m is None:
            tmp = self.summaryText[0:200]
            log.error("parse Summary failed: '%s'", tmp)
            raise FpdbParseError

        mg = m.groupdict()
        if "SITE" in mg:
            if self.site_name_map.get(mg["SITE"]) is not None:
                self.siteName = self.site_name_map.get(mg["SITE"])
                self.siteId = self.SITEIDS.get(self.siteName)
            else:
                tmp = self.summaryText[0:200]
                log.error("Unsupported site summary '%s'", tmp)
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
            t1 = self.re_max.search(self.tourneyName)
            if t1:
                self.maxseats = int(t1.group("MAX"))
            t2 = self.re_speed.search(self.tourneyName)
            if t2:
                if t2.group("SPEED") == "Turbo":
                    self.speed = "Turbo"
                elif t2.group("SPEED") == "Hyper-Turbo":
                    self.speed = "Hyper"
            t3 = self.re_sng.search(self.tourneyName)
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
            m1 = self.re_date_time.finditer(mg["DATETIME"])
            for a in m1:
                datetimestr = "{}/{}/{} {}:{}:{}".format(
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
            datetimestr,
            "%Y/%m/%d %H:%M:%S",
        ).replace(tzinfo=datetime.timezone.utc)  # also timezone at end, e.g. " ET"

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
            self.prizepool = int(Decimal(self.clearMoneyString(mg["BUYIN"]))) * int(
                self.entries,
            )

        m = self.re_player.finditer(self.summaryText)
        for a in m:
            mg = a.groupdict()
            name = mg["NAME"]
            rank = int(mg["RANK"])
            winnings = 0
            rebuy_count = None
            add_on_count = None
            ko_count = None
            if len(name) > 0:
                if "WINNINGS" in mg and mg["WINNINGS"] is not None:
                    winnings = int(100 * float(self.clearMoneyString(mg["WINNINGS"])))

                if "REBUYS" in mg and mg["REBUYS"] is not None:
                    rebuy_count = int(mg["REBUYS"])

                if "ADDONS" in mg and mg["ADDONS"] is not None:
                    add_on_count = int(mg["ADDONS"])

                if "KOS" in mg and mg["KOS"] is not None:
                    ko_count = int(mg["KOS"])

                if "CUR" in mg and mg["CUR"] is not None:
                    if mg["CUR"] == "$":
                        self.currency = "USD"
                    elif mg["CUR"] == "€":
                        self.currency = "EUR"
                    elif mg["CUR"] in ("P", "SC"):
                        self.currency = "PSFP"

                if rank == 0:
                    rank = None
                    winnings = None

                if len(name) == 0:
                    log.debug("a.groupdict(): %s", mg)

                self.addPlayer(
                    rank,
                    name,
                    winnings,
                    self.currency,
                    rebuy_count,
                    add_on_count,
                    ko_count,
                )
