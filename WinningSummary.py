"""Winning poker specific summary parsing code.

Copyright 2016 Chaz Littlejohn
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
from typing import Any, ClassVar

from past.utils import old_div

from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger
from TourneySummary import TourneySummary

# Winning HH Format
log = get_logger("winning_summary_parser")


class WinningSummary(TourneySummary):
    """Winning poker tournament summary parser."""

    sym: ClassVar = {"USD": r"\$", "T$": "", "play": ""}
    substitutions: ClassVar = {
        "LEGAL_ISO": "TB|CP",  # legal ISO currency codes
        "LS": r"\$|",  # legal currency symbols
        "PLYR": r"(?P<PNAME>.+?)",
        "NUM": r".,\dK",
    }
    games: ClassVar = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha HiLow": ("hold", "omahahilo"),
        "Seven Cards Stud": ("stud", "studhi"),
        "Seven Cards Stud HiLow": ("stud", "studhilo"),
    }

    speeds: ClassVar = {"Turbo": "Turbo", "Hyper Turbo": "Hyper", "Regular": "Normal"}

    re_identify = re.compile(r'<link\sid="ctl00_CalendarTheme"')

    re_html_player = re.compile(
        r"Player\sDetails:\s{PLYR}</a>".format(**substitutions),
        re.IGNORECASE,
    )

    re_html_tourney_info = re.compile(
        r"<td>(?P<TOURNO>[0-9]+)</td>"
        r"<td>(?P<GAME>Hold\'em|Omaha|Omaha\sHiLow|Seven\sCards\sStud|Seven\sCards\sStud\sHiLow)</td>"
        r"<td>(?P<TOURNAME>.*)</td>"
        r"<td>(?P<CURRENCY>[{LS}])(?P<BUYIN>[{NUM}]+)</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{LS}](?P<FEE>[{NUM}]+)</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{LS}](?P<REBUYS>[{NUM}]+)</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{LS}](?P<ADDONS>[{NUM}]+)</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{LS}](?P<WINNINGS>[{NUM}]+)</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>[{NUM}]+</td>"
        r"<td>.*</td>"
        r"<td>(?P<TOURNEYSTART>.*)</td>"
        r"<td>(?P<TOURNEYEND>.*)</td>"
        r"<td>.*</td>".format(**substitutions),  # duration
        re.VERBOSE | re.IGNORECASE,
    )

    re_html_tourney_extra_info = re.compile(
        r"""
        ^([{LS}]|)?(?P<GUAR>[{NUM}]+)\s
        ((?P<GAMEEXTRA>Holdem|PLO|PLO8|Omaha\sHi/Lo|Omaha|PL\sOmaha|PL\sOmaha\sHi/Lo|PLO\sHi/Lo)\s?)?
        ((?P<SPECIAL>(GTD|Freeroll|FREEBUY|Freebuy))\s?)?
        ((?P<SPEED>(Turbo|Hyper\sTurbo|Regular))\s?)?
        ((?P<MAX>(\d+\-Max|Heads\-up|Heads\-Up))\s?)?
        (?P<OTHER>.*?)
        """.format(**substitutions),
        re.VERBOSE | re.MULTILINE,
    )

    re_html_date_time = re.compile(
        r"(?P<M>[0-9]+)\/(?P<D>[0-9]+)\/(?P<Y>[0-9]{4})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+) (?P<AMPM>(AM|PM))",  # noqa: E501
        re.MULTILINE,
    )
    re_html_tour_no = re.compile(r"\s+<td>(?P<TOURNO>[0-9]+)</td>", re.DOTALL)

    codepage: ClassVar = ["utf8", "cp1252"]

    @staticmethod
    def getSplitRe(_head: str) -> re.Pattern[str]:
        """Get regex pattern for splitting tournament summaries."""
        return re.compile("</tr><tr")

    def parseSummary(self) -> None:
        """Parse tournament summary text."""
        info: dict[str, Any] = {}
        m1 = self.re_html_player.search(self.header)
        m2 = self.re_html_tourney_info.search(self.summaryText)
        if m1 is None or m2 is None:
            if self.re_html_tour_no.search(self.summaryText):
                tmp1 = self.header[0:200] if m1 is None else "NA"
                tmp2 = self.summaryText[0:200] if m2 is None else "NA"
                log.error("parse Summary Html failed: '%s' '%s'", tmp1, tmp2)
                raise FpdbParseError
            raise FpdbHandPartial
        info.update(m1.groupdict())
        info.update(m2.groupdict())
        self.parseSummaryArchive(info)

    def parseSummaryArchive(self, info: dict[str, Any]) -> None:  # noqa: PLR0912, PLR0915, C901
        """Parse tournament archive information."""
        if "TOURNAME" in info and info["TOURNAME"] is not None:
            self.tourneyName = info["TOURNAME"]
            m3 = self.re_html_tourney_extra_info.search(self.tourneyName)
            if m3 is not None:
                info.update(m3.groupdict())

        if "GAME" in info:
            self.gametype["category"] = self.games[info["GAME"]][1]

        if self.gametype["category"] == "holdem":
            self.gametype["limitType"] = "nl"
        elif self.gametype["category"] == "omaha":
            self.gametype["limitType"] = "pl"
        else:
            self.gametype["limitType"] = "fl"

        self.buyinCurrency = "USD"
        if "SPECIAL" in info and info["SPECIAL"] is not None:
            if info["SPECIAL"] in ("Freeroll", "FREEBUY", "Freebuy"):
                self.buyinCurrency = "FREE"
            self.guaranteeAmt = int(100 * Decimal(self.clearMoneyString(info["GUAR"])))

        if "TOURNO" in info:
            self.tourNo = info["TOURNO"]
        if info["BUYIN"] is not None:
            self.buyin = int(100 * Decimal(self.clearMoneyString(info["BUYIN"])))
        if info["FEE"] is not None:
            self.fee = int(100 * Decimal(self.clearMoneyString(info["FEE"])))

        if "REBUYS" in info and Decimal(self.clearMoneyString(info["REBUYS"].replace(" ", ""))) > 0:
            self.isRebuy = True
            self.rebuyCost = self.buyin

        if "ADDONS" in info and Decimal(self.clearMoneyString(info["ADDONS"].replace(" ", ""))) > 0:
            self.isAddOn = True
            self.addOnCost = self.buyin

        if "MAX" in info and info["MAX"] is not None:
            n = info["MAX"].replace("-Max", "")
            if n in ("Heads-up", "Heads-Up"):
                self.maxseats = 2
            else:
                self.maxseats = int(n)
        else:
            self.maxseats = 10

        if "SPEED" in info and info["SPEED"] is not None:
            self.speed = self.speeds[info["SPEED"]]
            self.isSng = True

        if "On Demand" in self.tourneyName:
            self.isOnDemand = True

        if " KO" in self.tourneyName or "Knockout" in self.tourneyName:
            self.isKO = True

        if "R/A" in self.tourneyName:
            self.isRebuy = True
            self.isAddOn = True
            self.addOnCost = self.buyin
            self.rebuyCost = self.buyin

        if "TOURNEYSTART" in info:
            m4 = self.re_html_date_time.finditer(info["TOURNEYSTART"])
            datetimestr = None  # default used if time not found
            for a in m4:
                datetimestr = "{}/{}/{} {}:{}:{} {}".format(
                    a.group("Y"),
                    a.group("M"),
                    a.group("D"),
                    a.group("H"),
                    a.group("MIN"),
                    a.group("S"),
                    a.group("AMPM"),
                )
                self.startTime = datetime.datetime.strptime(
                    datetimestr,
                    "%Y/%m/%d %I:%M:%S %p",
                ).replace(tzinfo=datetime.timezone.utc)  # also timezone at end, e.g. " ET"
                self.startTime = HandHistoryConverter.changeTimezone(
                    self.startTime,
                    self.import_parameters["timezone"],
                    "UTC",
                )

        if "TOURNEYEND" in info:
            m5 = self.re_html_date_time.finditer(info["TOURNEYEND"])
            datetimestr = None  # default used if time not found
            for a in m5:
                datetimestr = "{}/{}/{} {}:{}:{} {}".format(
                    a.group("Y"),
                    a.group("M"),
                    a.group("D"),
                    a.group("H"),
                    a.group("MIN"),
                    a.group("S"),
                    a.group("AMPM"),
                )
                self.endTime = datetime.datetime.strptime(
                    datetimestr,
                    "%Y/%m/%d %I:%M:%S %p",
                ).replace(tzinfo=datetime.timezone.utc)  # also timezone at end, e.g. " ET"
                self.endTime = HandHistoryConverter.changeTimezone(
                    self.endTime,
                    self.import_parameters["timezone"],
                    "UTC",
                )

        self.currency = "USD"
        winnings = 0
        rebuy_count = None
        add_on_count = None
        ko_count = None
        rank = 9999  # fix with lookups

        if "WINNINGS" in info and info["WINNINGS"] is not None:
            winnings = int(100 * Decimal(self.clearMoneyString(info["WINNINGS"])))

        if self.isRebuy and self.rebuyCost > 0:
            rebuy_amt = int(
                100 * Decimal(self.clearMoneyString(info["REBUYS"].replace(" ", ""))),
            )
            rebuy_count = old_div(rebuy_amt, self.rebuyCost)

        if self.isAddOn and self.addOnCost > 0:
            add_on_amt = int(
                100 * Decimal(self.clearMoneyString(info["ADDONS"].replace(" ", ""))),
            )
            add_on_count = old_div(add_on_amt, self.addOnCost)

        self.hero = info["PNAME"]

        self.addPlayer(
            rank,
            info["PNAME"],
            winnings,
            self.currency,
            rebuy_count,
            add_on_count,
            ko_count,
        )
