"""Bovada tournament summary parser.

Copyright 2008-2013 Chaz Littlejohn
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

import BovadaToFpdb
from HandHistoryConverter import FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger
from TourneySummary import TourneySummary

log = get_logger("parser")


class BovadaSummary(TourneySummary):
    """Bovada tournament summary parser."""

    substitutions: ClassVar = {
        "LEGAL_ISO": "USD",  # legal ISO currency codes
        "LS": r"\$|",  # legal currency symbols - Euro(cp1252, utf-8)
        "PLYR": r"(?P<PNAME>.+?)",
        "PLYR1": r"(?P<PNAME1>.+?)",
        "CUR": r"(\$|)",
        "NUM": r".,\d",
    }
    codepage = ("utf8", "cp1252")

    re_identify = re.compile(r"(Ignition|Bovada|Bodog(\.eu|\sUK|\sCanada|88)?)\sHand")
    re_add_on = re.compile(
        r"^{PLYR}  ?\[ME\] : Addon (?P<ADDON>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_rebuyin = re.compile(
        r"{PLYR}  ?\[ME\] : Rebuyin (?P<REBUY>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_ranking = re.compile(
        (
            r"{PLYR}  ?\[ME\] : Ranking (?P<RANK>[{NUM}]+)"
            r"(\s+?{PLYR1}  ?\[ME\] : Prize Cash \[(?P<WINNINGS>{CUR}[{NUM}]+)\])?"
        ).format(**substitutions),
        re.MULTILINE,
    )
    re_stand = re.compile(r"{PLYR}  ?\[ME\] : Stand".format(**substitutions), re.MULTILINE)

    @staticmethod
    def get_split_re() -> re.Pattern[str]:
        """Get regex pattern for splitting tournament summaries."""
        return re.compile("PokerStars Tournament ")

    def parseSummary(self) -> None:  # noqa: PLR0912, PLR0915, C901
        """Parse tournament summary text."""
        obj = getattr(BovadaToFpdb, "Bovada", None)
        hhc = obj(self.config, in_path=self.in_path, sitename=None, autostart=False)
        m = hhc.re_GameInfo.search(self.summaryText)
        if m is None:
            tmp = self.summaryText[0:200]
            log.error("parseSummary not found: '%s'", tmp)
            raise FpdbParseError

        info = {}
        info.update(m.groupdict())
        m = hhc.re_Buyin.search(self.in_path)
        if m:
            info.update(m.groupdict())

        if info["TOURNO"] is None:
            tmp = self.summaryText[0:200]
            log.error("Text does not appear to be a tournament '%s'", tmp)
            raise FpdbParseError
        self.tourNo = info["TOURNO"]
        if "LIMIT" in info:
            if not info["LIMIT"]:
                self.gametype["limitType"] = "nl"
            else:
                self.gametype["limitType"] = hhc.limits[info["LIMIT"]]
        if "GAME" in info:
            self.gametype["category"] = hhc.games[info["GAME"]][1]

        if info.get("CURRENCY"):
            self.buyinCurrency = hhc.currencies[info["CURRENCY"]]
        self.currency = self.buyinCurrency

        if "DATETIME" in info and info["CURRENCY"] is not None:
            m1 = hhc.re_DateTime.finditer(info["DATETIME"])
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
            self.startTime = datetime.datetime.strptime(
                datetimestr, "%Y/%m/%d %H:%M:%S",
            ).replace(tzinfo=datetime.timezone.utc)
            self.startTime = HandHistoryConverter.changeTimezone(
                self.startTime, "ET", "UTC",
            )

        self.buyin = 0
        self.fee = 0
        self.prizepool = None
        self.entries = None

        if self.currency is None:
            self.buyinCurrency = "FREE"

        if "BUYIN" in info and info["BUYIN"] is not None and info["BIAMT"] is not None and info["BIRAKE"] is not None:
                if info["BUYIN"].find("$") != -1:
                    self.buyinCurrency = "USD"
                elif re.match("^[0-9+]*$", info["BUYIN"]):
                    self.buyinCurrency = "play"
                else:
                    log.error("Failed to detect currency")
                    raise FpdbParseError
                self.currency = self.buyinCurrency

                info["BIAMT"] = hhc.clearMoneyString(info["BIAMT"].strip("$"))

                if info["BIRAKE"]:
                    info["BIRAKE"] = hhc.clearMoneyString(info["BIRAKE"].strip("$"))
                else:
                    info["BIRAKE"] = "0"

                if info["TICKET"] is None:
                    self.buyin = int(100 * Decimal(info["BIAMT"]))
                    self.fee = int(100 * Decimal(info["BIRAKE"]))
                else:
                    self.buyin = 0
                    self.fee = 0

                if info["TOURNAME"] is not None:
                    tourney_name_full = (
                        info["TOURNAME"]
                        + " - "
                        + info["BIAMT"]
                        + "+"
                        + info["BIRAKE"]
                    )
                    self.tourneyName = tourney_name_full

                    if "TOURNAME" in info and "Rebuy" in info["TOURNAME"]:
                        self.isAddOn, self.isRebuy = True, True
                        self.rebuyCost = self.buyin
                        self.addOnCost = self.buyin

        rebuys, addons, winnings = None, None, []
        m = self.re_ranking.finditer(self.summaryText)
        for i, a in enumerate(m):
            mg = a.groupdict()
            winnings.append([int(mg["RANK"]), 0])
            if mg["WINNINGS"] is not None:
                if mg["WINNINGS"].find("$") != -1:
                    self.currency = "USD"
                elif re.match("^[0-9+]*$", mg["WINNINGS"]):
                    self.currency = "play"
                winnings[i][1] = int(
                    100 * Decimal(self.clearMoneyString(mg["WINNINGS"])),
                )

        m = self.re_rebuyin.finditer(self.summaryText)
        for _a in m:
            if rebuys is None:
                rebuys = 0
            rebuys += 1

        m = self.re_add_on.finditer(self.summaryText)
        for _a in m:
            if addons is None:
                addons = 0
            addons += 1

        for i, win in enumerate(winnings):
            rank_id = i + 1 if len(win) > 1 else None
            if i == 0:
                self.addPlayer(
                    win[0], "Hero", win[1], self.currency, rebuys, addons, rank_id,
                )
            else:
                self.addPlayer(win[0], "Hero", win[1], self.currency, 0, 0, rank_id)
