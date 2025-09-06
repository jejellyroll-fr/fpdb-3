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

log = get_logger("bovada_summary_parser")


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
        """Return a compiled regular expression for splitting tournament summaries.

        This static method provides a regex pattern used to identify the start of each tournament summary section.

        Returns:
            re.Pattern[str]: The compiled regular expression for splitting summaries.
        """
        return re.compile("PokerStars Tournament ")  # This is a placeholder for the actual split regex.

    def _get_summary_excerpt(self) -> str:
        """Return a short excerpt from the tournament summary text.

        This method provides the first 200 characters of the summary for logging or error reporting purposes.

        Returns:
            str: The first 200 characters of the summary text.
        """
        return self.summaryText[:200]

    def _raise_parse_error(self, message: str) -> None:
        """Log an error and raise an FpdbParseError with a summary excerpt.

        This method logs the provided error message along with a short excerpt of the summary,
        then raises an FpdbParseError to indicate a parsing failure.

        Args:
            message: The error message to log and include with the exception.

        Raises:
            FpdbParseError: Always raised to signal a parsing error.
        """
        tmp = self._get_summary_excerpt()
        log.error(message, tmp)
        raise FpdbParseError

    def _detect_currency(self, buyin_info: str) -> str:
        """Detect the currency type from the buy-in information string.

        This method returns 'USD' if a dollar sign is present, 'play' if the string contains only digits or plus signs,
        or raises an FpdbParseError if the currency cannot be determined.

        Args:
            buyin_info: The buy-in information string to analyze.

        Returns:
            str: The detected currency type ('USD' or 'play').

        Raises:
            FpdbParseError: If the currency cannot be detected from the input string.
        """
        if "$" in buyin_info:
            return "USD"
        if re.match("^[0-9+]*$", buyin_info):
            return "play"
        self._raise_parse_error("Failed to detect currency")
        return ""  # This line is never reached but satisfies linter

    def _process_buyin_info(self, info: dict, hhc: HandHistoryConverter) -> None:
        """Process and assign buy-in, fee, and tournament name information.

        This method detects the currency, processes buy-in and fee amounts,
        and sets tournament name and rebuy/add-on flags
        based on the provided info dictionary and hand history converter.

        Args:
            info: A dictionary containing buy-in, fee, ticket, and tournament name information.
            hhc: The hand history converter used to process monetary values.
        """
        self.buyinCurrency = self._detect_currency(info["BUYIN"])
        self.currency = self.buyinCurrency

        info["BIAMT"] = hhc.clearMoneyString(info["BIAMT"].strip("$"))
        info["BIRAKE"] = hhc.clearMoneyString(info["BIRAKE"].strip("$")) if info["BIRAKE"] else "0"

        if info["TICKET"] is None:
            self.buyin = int(100 * Decimal(info["BIAMT"]))
            self.fee = int(100 * Decimal(info["BIRAKE"]))
        else:
            self.buyin = 0
            self.fee = 0

        if info["TOURNAME"] is not None:
            self.tourneyName = f"{info['TOURNAME']} - {info['BIAMT']}+{info['BIRAKE']}"
            if "Rebuy" in info["TOURNAME"]:
                self.isAddOn, self.isRebuy = True, True
                self.rebuyCost = self.buyin
                self.addOnCost = self.buyin

    def _process_winnings(self) -> list:
        """Extract and process player winnings from the tournament summary text.

        This method parses the summary text for ranking and winnings information, updates the currency,
        and returns a list of player ranks and their corresponding winnings.

        Returns:
            list: A list of [rank, winnings] pairs for each player found in the summary.
        """
        winnings = []
        m = self.re_ranking.finditer(self.summaryText)
        for i, a in enumerate(m):
            mg = a.groupdict()
            winnings.append([int(mg["RANK"]), 0])
            if mg["WINNINGS"] is not None:
                self.currency = self._detect_currency(mg["WINNINGS"])
                winnings[i][1] = int(100 * Decimal(self.clearMoneyString(mg["WINNINGS"])))
        return winnings

    def _count_rebuys_and_addons(self) -> tuple[int | None, int | None]:
        """Extract and process player winnings from the tournament summary text.

        This method parses the summary text for ranking and winnings information, updates the currency,
        and returns a list of player ranks and their corresponding winnings.

        Returns:
            list: A list of [rank, winnings] pairs for each player found in the summary.
        """
        rebuys = addons = None

        for _ in self.re_rebuyin.finditer(self.summaryText):
            rebuys = (rebuys or 0) + 1

        for _ in self.re_add_on.finditer(self.summaryText):
            addons = (addons or 0) + 1

        return rebuys, addons

    def _process_datetime(self, info: dict, hhc: HandHistoryConverter) -> None:
        """Parse and set the tournament start time from the info dictionary.

        This method extracts the date and time from the info dictionary using the hand history converter's regex,
        sets the startTime attribute, and converts it to UTC timezone.

        Args:
            info: A dictionary containing tournament information, including 'DATETIME' and 'CURRENCY'.
            hhc: The hand history converter providing the date-time regex and timezone conversion.
        """
        if "DATETIME" not in info or info["CURRENCY"] is None:
            return

        m1 = hhc.re_DateTime.finditer(info["DATETIME"])
        datetimestr = "2000/01/01 00:00:00"  # default used if time not found
        for a in m1:
            datetimestr = (
                f"{a.group('Y')}/{a.group('M')}/{a.group('D')} " f"{a.group('H')}:{a.group('MIN')}:{a.group('S')}"
            )
        self.startTime = datetime.datetime.strptime(
            datetimestr,
            "%Y/%m/%d %H:%M:%S",
        ).replace(tzinfo=datetime.timezone.utc)
        self.startTime = HandHistoryConverter.changeTimezone(
            self.startTime,
            "ET",
            "UTC",
        )

    def _initialize_base_properties(self) -> None:
        """Initialize base tournament properties to default values.

        This method sets the buy-in, fee, prize pool, and entries to their default states,
        and assigns 'FREE' as the buy-in currency if no currency is set.
        """
        self.buyin = 0
        self.fee = 0
        self.prizepool = None
        self.entries = None

        if self.currency is None:
            self.buyinCurrency = "FREE"

    def _process_game_info(self, info: dict, hhc: HandHistoryConverter) -> None:
        """Process and assign game type and currency information from the summary.

        This method sets the game type's limit and category, and updates the buy-in currency and currency
        based on the provided info dictionary and hand history converter.

        Args:
            info: A dictionary containing game and currency information.
            hhc: The hand history converter providing mappings for limits, games, and currencies.
        """
        if "LIMIT" in info:
            self.gametype["limitType"] = hhc.limits[info["LIMIT"]] if info["LIMIT"] else "nl"
        if "GAME" in info:
            self.gametype["category"] = hhc.games[info["GAME"]][1]

        if info.get("CURRENCY"):
            self.buyinCurrency = hhc.currencies[info["CURRENCY"]]
        self.currency = self.buyinCurrency

    def _process_players(self, winnings: list, rebuys: int | None, addons: int | None) -> None:
        """Add players to the summary based on winnings, rebuys, and addons.

        This method iterates through the winnings list and adds each player to the summary,
        assigning rebuys and addons to the first player and defaulting to zero for others.

        Args:
            winnings: A list of [rank, winnings] pairs for each player.
            rebuys: The number of rebuys for the first player, or None.
            addons: The number of addons for the first player, or None.
        """
        for i, win in enumerate(winnings):
            rank_id = i + 1 if len(win) > 1 else None
            if i == 0:
                self.addPlayer(
                    win[0],
                    "Hero",
                    win[1],
                    self.currency,
                    rebuys,
                    addons,
                    rank_id,
                )
            else:
                self.addPlayer(win[0], "Hero", win[1], self.currency, 0, 0, rank_id)

    def parseSummary(self) -> None:
        """Parse the tournament summary and populate summary attributes.

        This method extracts game, buy-in, player, and winnings information from the summary text,
        processes and assigns all relevant tournament attributes, and adds players to the summary.

        Raises:
            FpdbParseError: If required information cannot be found or parsed from the summary.
        """
        obj = getattr(BovadaToFpdb, "Bovada", None)
        hhc = obj(self.config, in_path=self.in_path, sitename=None, autostart=False)
        m = hhc.re_GameInfo.search(self.summaryText)
        if m is None:
            self._raise_parse_error("parseSummary not found: '%s'")

        info = m.groupdict()
        if m := hhc.re_Buyin.search(self.in_path):
            info = info | m.groupdict()

        if info["TOURNO"] is None:
            self._raise_parse_error("Text does not appear to be a tournament '%s'")
        self.tourNo = info["TOURNO"]

        self._process_game_info(info, hhc)
        self._process_datetime(info, hhc)
        self._initialize_base_properties()

        if "BUYIN" in info and info["BUYIN"] is not None and info["BIAMT"] is not None and info["BIRAKE"] is not None:
            self._process_buyin_info(info, hhc)

        winnings = self._process_winnings()
        rebuys, addons = self._count_rebuys_and_addons()
        self._process_players(winnings, rebuys, addons)
