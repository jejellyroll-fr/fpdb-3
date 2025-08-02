"""Pacific Poker tournament summary parser.

Copyright 2008-2012 Steffen Schaumburg
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

import re
from decimal import Decimal
from typing import ClassVar

from HandHistoryConverter import FpdbParseError
from loggingFpdb import get_logger
from TourneySummary import TourneySummary

# Pacifc(888) HH Format
log = get_logger("pacific_poker_summary_parser")


class PacificPokerSummary(TourneySummary):
    """Pacific Poker tournament summary parser."""

    limits: ClassVar = {"No Limit": "nl", "Pot Limit": "pl", "Limit": "fl", "LIMIT": "fl"}

    games: ClassVar = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "Holdem": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi/Lo": ("hold", "omahahilo"),
        "OmahaHL": ("hold", "omahahilo"),
    }

    substitutions: ClassVar = {
        "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP",  # legal ISO currency codes
        "LS": r"\$|€|",  # legal currency symbols
        "NUM": ".,\\d\xa0",  # legal characters in number format
    }

    re_identify = re.compile(
        r"\*{5}\s(Cassava|888poker|888)(\.[a-z]{2})?(\-[a-z]{2})? Tournament Summary\s\*{5}",
    )

    re_tourney_info = re.compile(
        r"""
                        Tournament\sID:\s(?P<TOURNO>[0-9]+)\s+
                        Buy-In:\s(?P<BUYIN>(((?P<BIAMT>(?P<CURRENCY1>{LS})?[{NUM}]+\s?(?P<CURRENCY2>{LS})?)(\s\+\s?(?P<BIRAKE>({LS})?[{NUM}]+\s?({LS})?))?)|(Free)|(.+?)))\s+
                        (Rebuy:\s[{LS}](?P<REBUYAMT>[{NUM}]+)\s?({LS})?\s+)?
                        (Add-On:\s[{LS}](?P<ADDON>[{NUM}]+)\s?({LS})?\s+)?
                        ((?P<P1NAME>.*?)\sperformed\s(?P<PREBUYS>\d+)\srebuys?\s+)?
                        ((?P<P2NAME>.*?)\sperformed\s(?P<PADDONS>\d+)\sadd-ons?\s+)?
                        ^(?P<PNAME>.+?)\sfinished\s(?P<RANK>[0-9]+)\/(?P<ENTRIES>[0-9]+)(\sand\swon\s(?P<WCURRENCY>[{LS}])?(?P<WINNINGS>[{NUM}]+)\s?(?P<WCURRENCY2>[{LS}])?)?
                               """.format(**substitutions),
        re.VERBOSE | re.MULTILINE | re.DOTALL,
    )

    re_category = re.compile(
        """
          (?P<LIMIT>No\\sLimit|Fix\\sLimit|Pot\\sLimit)\\s
          (?P<GAME>Holdem|Omaha|OmahaHL|Hold\'em|Omaha\\sHi/Lo|OmahaHL)
                               """.format(),
        re.VERBOSE | re.MULTILINE | re.DOTALL,
    )

    codepage = ("utf8", "cp1252")

    @staticmethod
    def get_split_re() -> re.Pattern[str]:
        """Get regex pattern for splitting tournament summaries."""
        return re.compile(
            r"\*\*\*\*\* (Cassava|888poker|888)(\.[a-z]{2})?(\-[a-z]{2})? Tournament Summary \*\*\*\*\*",
        )

    def parseSummary(self) -> None:  # noqa: PLR0915, PLR0912, C901
        """Parse tournament summary text."""
        m = self.re_tourney_info.search(self.summaryText)
        if m is None:
            tmp = self.summaryText[0:200]
            log.error("parseSummary failed: '%s'", tmp)
            raise FpdbParseError

        mg = m.groupdict()

        self.tourNo = mg["TOURNO"]

        m1 = self.re_category.search(self.in_path)
        if m1:
            mg1 = m1.groupdict()
            if "LIMIT" in mg1 and mg1["LIMIT"] is not None:
                self.gametype["limitType"] = self.limits[mg1["LIMIT"]]
            else:
                self.gametype["limitType"] = "fl"
            if "GAME" in mg1:
                self.gametype["category"] = self.games[mg1["GAME"]][1]
        else:
            self.gametype["limitType"] = "nl"
            self.gametype["category"] = "holdem"

        if "BUYIN" in mg and mg["BUYIN"] is not None:
            if mg["BUYIN"] == "Free" or mg["BIAMT"] is None:
                self.buyin = 0
                self.fee = 0
            else:
                self.buyin = int(100 * self.convert_to_decimal(mg["BIAMT"]))
                if mg["BIRAKE"] is None:
                    self.fee = 0
                else:
                    self.fee = int(100 * self.convert_to_decimal(mg["BIRAKE"]))

        self.entries = mg["ENTRIES"]
        self.prizepool = self.buyin * int(self.entries)
        if "REBUYAMT" in mg and mg["REBUYAMT"] is not None:
            self.isRebuy = True
            self.rebuyCost = int(100 * self.convert_to_decimal(mg["REBUYAMT"]))
        if "ADDON" in mg and mg["ADDON"] is not None:
            self.isAddOn = True
            self.addOnCost = int(100 * self.convert_to_decimal(mg["ADDON"]))

        if mg.get("CURRENCY1"):
            currency = mg["CURRENCY1"]
        elif mg.get("CURRENCY2"):
            currency = mg["CURRENCY2"]
        else:
            currency = None

        if currency:
            if currency == "$":
                self.buyinCurrency = "USD"
            elif currency == "€":
                self.buyinCurrency = "EUR"
        elif self.buyin == 0:
            self.buyinCurrency = "FREE"
        else:
            self.buyinCurrency = "play"
        self.currency = self.buyinCurrency

        player = mg["PNAME"]
        rank = int(mg["RANK"])
        winnings = 0
        rebuy_count = None
        add_on_count = None
        ko_count = None

        if "WINNINGS" in mg and mg["WINNINGS"] is not None:
            winnings = int(100 * self.convert_to_decimal(mg["WINNINGS"]))
            if mg.get("WCURRENCY"):
                if mg["WCURRENCY"] == "$":
                    self.currency = "USD"
                elif mg["WCURRENCY"] == "€":
                    self.currency = "EUR"
            elif mg.get("WCURRENCY2"):
                if mg["WCURRENCY2"] == "$":
                    self.currency = "USD"
                elif mg["WCURRENCY2"] == "€":
                    self.currency = "EUR"
        if "PREBUYS" in mg and mg["PREBUYS"] is not None:
            rebuy_count = int(mg["PREBUYS"])
        if "PADDONS" in mg and mg["PADDONS"] is not None:
            add_on_count = int(mg["PADDONS"])

        self.addPlayer(
            rank, player, winnings, self.currency, rebuy_count, add_on_count, ko_count,
        )

    def convert_to_decimal(self, string: str) -> Decimal:
        """Convert money string to decimal."""
        dec = self.clearMoneyString(string)
        return Decimal(dec)
