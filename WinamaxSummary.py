"""Winamax tournament summary parser.

Copyright 2008-2011 Carl Gherardi
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

from bs4 import BeautifulSoup

from HandHistoryConverter import FpdbParseError
from loggingFpdb import get_logger
from TourneySummary import TourneySummary

# Winamax HH Format
log = get_logger("winamax_summary_parser")


class WinamaxSummary(TourneySummary):
    """Winamax tournament summary parser."""

    limits: ClassVar = {"No Limit": "nl", "Pot Limit": "pl", "Limit": "fl", "LIMIT": "fl"}
    games: ClassVar = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "5 Card Omaha": ("hold", "5_omahahi"),
        "Omaha 5": ("hold", "5_omahahi"),
        "5 Card Omaha Hi/Lo": ("hold", "5_omahahi"),  # incorrect in file
        "Omaha Hi/Lo": ("hold", "omahahilo"),
        "7-Card Stud": ("stud", "studhi"),
        "7-Card Stud Hi/Lo": ("stud", "studhilo"),
        "Razz": ("stud", "razz"),
        "2-7 Triple Draw": ("draw", "27_3draw"),
    }

    substitutions: ClassVar = {
        "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP",  # legal ISO currency codes
        "LS": r"\$|€|",  # legal currency symbols
    }

    re_identify = re.compile(r"Winamax\sPoker\s\-\sTournament\ssummary")

    re_summary_tourney_info = re.compile(
        r"""\s:\s
            ((?P<LIMIT>No\sLimit|Limit|LIMIT|Pot\sLimit)\s)?
            (?P<GAME>.+)?
            \((?P<TOURNO>[0-9]+)\)(\s-\sLate\s(r|R)egistration)?\s+
            (Player\s:\s(?P<PNAME>.*)\s+)?
            Buy-In\s:\s(?P<BUYIN>(?P<BIAMT>.+?)\s\+\s(?P<BIRAKE>.+?)(\s\+\s(?P<BIBOUNTY>.+))?|Freeroll|Gratuit|Ticket\suniquement|Free|Ticket)\s+
            (Rebuy\scost\s:\s(?P<REBUY>(?P<REBUYAMT>.+)\s\+\s(?P<REBUYRAKE>.+))\s+)?
            (Addon\scost\s:\s(?P<ADDON>(?P<ADDONAMT>.+)\s\+\s(?P<ADDONRAKE>.+))\s+)?
            (Your\srebuys\s:\s(?P<PREBUYS>\d+)\s+)?
            (Your\saddons\s:\s(?P<PADDONS>\d+)\s+)?
            Registered\splayers\s:\s(?P<ENTRIES>[0-9]+)\s+
            (Total\srebuys\s:\s\d+\s+)?
            (Total\saddons\s:\s\d+\s+)?
            (Prizepool\s:\s(?P<PRIZEPOOL1>[.0-9{LS}]+)\s+)?
            (Mode\s:\s(?P<MODE>.+)?\s+)?
            (Type\s:\s(?P<TYPE>.+)?\s+)?
            (Speed\s:\s(?P<SPEED>.+)?\s+)?
            (Flight\sID\s:\s.+\s+)?
            (Levels\s:\s(?P<LEVELS>.+)\s+)?
            (Total\srebuys\s:\s(?P<TREBUYS>\d+)\s+)?
            (Total\saddons\s:\s(?P<TADDONS>\d+)\s+)?
            (Prizepool\s:\s(?P<PRIZEPOOL2>[.0-9{LS}]+)\s+)?
            Tournament\sstarted\s(?P<DATETIME>[0-9]{{4}}\/[0-9]{{2}}\/[0-9]{{2}}\s[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}\sUTC)\s+
            (?P<BLAH>You\splayed\s.+)\s+
            You\sfinished\sin\s(?P<RANK>[.0-9]+)(st|nd|rd|th)?\splace\s+
            (You\swon\s((?P<WINNINGS>[.0-9{LS}]+))?(\s\+\s)?(Ticket\s(?P<TICKET>[.0-9{LS}]+))?(\s\+\s)?(Bounty\s(?P<BOUNTY>[.0-9{LS}]+))?)?
            """.format(**substitutions),
        re.VERBOSE | re.MULTILINE,
    )

    re_game_type = re.compile(
        """<h1>((?P<LIMIT>No Limit|Pot Limit) (?P<GAME>Hold\'em|Omaha))</h1>""",
    )

    re_tour_no = re.compile(r"ID\=(?P<TOURNO>[0-9]+)")

    re_player = re.compile(
        r"""(?P<RANK>\d+)<\/td><td width="30%">(?P<PNAME>.+?)<\/td><td width="60%">(?P<WINNINGS>.+?)</td>""",
    )

    re_details = re.compile("""<p class="text">(?P<LABEL>.+?) : (?P<VALUE>.+?)</p>""")
    re_prizepool = re.compile("""<div class="title2">.+: (?P<PRIZEPOOL>[0-9,]+)""")

    re_date_time = re.compile(
        r"\[(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)",
    )
    re_ticket = re.compile(
        """ / (?P<TTYPE>Ticket (?P<VALUE>[0-9.]+)&euro;|Tremplin Winamax Poker Tour|Starting Block Winamax Poker Tour|Finale Freeroll Mobile 2012|SNG Freeroll Mobile 2012)""",  # noqa: E501
    )

    codepage: ClassVar = ("utf8", "cp1252")
    hhtype: ClassVar = "summary"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initializes a WinamaxSummary instance.

        Sets up the tournament summary parser and initializes lottery-related fields to their default values.

        """
        super().__init__(*args, **kwargs)
        # Initialize lottery fields with default values
        self.isLottery = False
        self.tourneyMultiplier = 1

    def getSplitRe(self, head: str) -> re.Pattern[str]:
        """Returns the regular expression pattern used to split Winamax tournament summaries.

        This method provides a compiled regex pattern that identifies the start of a Winamax tournament summary.

        Args:
            head: The header portion of the file (unused but required by interface).

        Returns:
            re.Pattern[str]: Compiled regular expression for summary splitting.

        """
        return re.compile(r"Winamax\sPoker\s-\sTournament\ssummary")

    def parseSummary(self) -> None:
        """Parses the tournament summary based on the summary type.

        This method dispatches to the appropriate parser depending on whether the summary is in file or HTML format.

        """
        if self.hhtype == "summary":
            self.parseSummaryFile()
        elif self.hhtype == "html":
            self.parseSummaryHtml()

    def parseSummaryHtml(self) -> None:
        """Parses a Winamax tournament summary in HTML format.

        This method extracts tournament details, prizepool, game type, player information,
        and tournament number from the HTML summary.

        """
        soup = BeautifulSoup(self.summaryText)
        left_content = soup.findAll("div", {"class": "left_content"})

        self._parse_tournament_details(soup)
        self._parse_prizepool(soup)
        self._parse_gametype(left_content)
        self._parse_players(left_content)
        self._parse_tournament_number()

    def _parse_tournament_details(self, soup: BeautifulSoup) -> None:
        """Parses tournament details from the provided HTML soup.

        This method extracts and sets the buy-in, number of entries, and tournament start time from the summary HTML.

        Args:
            soup: BeautifulSoup object containing the tournament summary HTML.

        """
        text_paragraphs = soup.findAll("p", {"class": "text"})
        for paragraph in text_paragraphs:
            for match in self.re_details.finditer(str(paragraph)):
                match_groups = match.groupdict()
                label = match_groups["LABEL"]
                value = match_groups["VALUE"]

                if label == "Buy-in":
                    self._parse_buyin(value)
                elif label == "Nombre de joueurs inscrits":
                    self.entries = value
                elif label == "D\xc3\xa9but du tournoi":
                    self.startTime = datetime.datetime.strptime(
                        value,
                        "%d-%m-%Y %H:%M",
                    ).replace(tzinfo=datetime.timezone.utc)

    def _parse_buyin(self, value: str) -> None:
        """Parses the buy-in and fee from a value string.

        This method extracts and sets the buy-in and fee amounts from the provided string.

        Args:
            value: The string containing buy-in and fee information.

        """
        # Detect currency before cleaning the value
        detected_currency = self._determine_currency(value)
        self.currency = detected_currency
        self.buyinCurrency = detected_currency

        cleaned_value = value.replace("&euro;", "").replace("+", "").strip(" $")
        buyin_str, fee_str = cleaned_value.split(" ")
        self.buyin = int(100 * Decimal(buyin_str))
        self.fee = int(100 * Decimal(fee_str))

    def _parse_prizepool(self, soup: BeautifulSoup) -> None:
        """Parses the prizepool amount from the provided HTML soup.

        This method extracts and sets the prizepool value from the tournament summary HTML.

        Args:
            soup: BeautifulSoup object containing the tournament summary HTML.

        """
        title_divs = soup.findAll("div", {"class": "title2"})
        for match in self.re_prizepool.finditer(str(title_divs)):
            match_groups = match.groupdict()
            self.prizepool = match_groups["PRIZEPOOL"].replace(",", ".")

    def _parse_gametype(self, left_content: list[Any]) -> None:
        """Parses the game type from the provided HTML content.

        This method sets the limit type and category for the tournament based on the parsed game type information.

        Args:
            left_content: List of HTML elements containing game type information.

        """
        for match in self.re_game_type.finditer(str(left_content[0])):
            match_groups = match.groupdict()
            self.gametype["limitType"] = self.limits[match_groups["LIMIT"]]
            self.gametype["category"] = self.games[match_groups["GAME"]][1]
            return

        # Default gametype if not found
        log.warning("Gametype unknown defaulting to NLHE")
        self.gametype["limitType"] = "nl"
        self.gametype["category"] = "holdem"

    def _parse_players(self, left_content: list) -> None:
        """Parses player information from the provided HTML content.

        This method extracts player rank, name, and winnings from the summary and
        adds each player to the tournament summary.

        Args:
            left_content: List of HTML elements containing player information.

        """
        for match in self.re_player.finditer(str(left_content[0])):
            match_groups = match.groupdict()
            rank_str = match_groups["RANK"]

            if rank_str != "...":
                name = match_groups["PNAME"]
                rank = int(rank_str)
                winnings = self._calculate_winnings(match_groups["WINNINGS"])
                if winnings is not None:
                    winnings_cents = int(100 * Decimal(winnings))
                    self.addPlayer(rank, name, winnings_cents, self.currency, None, None, None)

    def _calculate_winnings(self, winnings_str: str) -> Decimal | None:
        """Calculates the winnings amount from a winnings string.

        This method extracts and returns the winnings as a decimal value,
        handling both cash and satellite ticket winnings.

        Args:
            winnings_str: The string containing winnings information.

        Returns:
            Decimal or None: The winnings amount as a Decimal, or None if not applicable.

        """
        if satellite_match := self.re_ticket.search(winnings_str):
            if satellite_match.group("VALUE"):
                winnings = self.convert_to_decimal(satellite_match.group("VALUE"))
                return winnings if winnings > 0 else None
            return None  # Value not specified for satellite
        return self.convert_to_decimal(winnings_str)

    def _parse_tournament_number(self) -> None:
        """Parses the tournament number from the summary text.

        This method extracts and sets the tournament number (tourNo) from the summary using a regular expression.

        """
        for match in self.re_tour_no.finditer(self.summaryText):
            match_groups = match.groupdict()
            self.tourNo = match_groups["TOURNO"]

    def _parse_gametype(self, mg: dict) -> None:
        """Parses the game type from a match group dictionary.

        This method sets the limit type and category for the tournament based on the provided match group information.
        If the information is incomplete, it attempts to parse from levels or falls back to default values.

        Args:
            mg: Dictionary containing parsed match group data.

        """
        if "LIMIT" in mg and mg["LIMIT"] is not None:
            self.gametype["limitType"] = self.limits[mg["LIMIT"]]
            self.gametype["category"] = self.games[mg["GAME"]][1]
        elif "LEVELS" in mg and mg["LEVELS"] is not None:
            # Parse gametype from Levels information
            if self._parse_gametype_from_levels(mg["LEVELS"]):
                return
            # If parsing from levels failed, fall back to defaults
            log.warning("Could not parse gametype from Levels, defaulting to NLHE")
            self._set_default_gametype(mg)
        else:
            log.warning("Gametype unknown defaulting to NLHE")
            self._set_default_gametype(mg)

    def _set_default_gametype(self, mg: dict) -> None:
        """Sets the default game type for the tournament.

        This method assigns default values for limit type, category,
        and tournament name when game type information is missing.

        Args:
            mg: Dictionary containing parsed match group data.

        """
        self.gametype["limitType"] = "nl"
        self.gametype["category"] = "holdem"
        self.tourneyName = mg.get("GAME", "Unknown")

    # Constants for parsing
    MIN_LEVEL_PARTS = 4

    def _parse_gametype_from_levels(self, levels_str: str) -> bool:
        """Parses gametype from Levels string.

        Extracts the game category and limit type from the levels information.
        Example: "[10-20:0:180:holdem-no-limit,...]" -> category: "holdem", limitType: "nl"

        Args:
            levels_str: The levels string from tournament summary.

        Returns:
            bool: True if parsing succeeded, False otherwise.
        """
        gametype_str = self._extract_gametype_string(levels_str)
        return self._parse_gametype_string(gametype_str) if gametype_str else False

    def _extract_gametype_string(self, levels_str: str) -> str:
        """Extracts the gametype string from the levels information.

        This method parses the levels string to retrieve the gametype portion for further processing.

        Args:
            levels_str: The levels string from tournament summary.

        Returns:
            str: The extracted gametype string, or an empty string if not found.

        """
        import re

        level_match = re.search(r"\[([^,\]]+)", levels_str)
        if not level_match:
            return ""

        first_level = level_match[1]
        parts = first_level.split(":")
        return parts[3] if len(parts) >= self.MIN_LEVEL_PARTS else ""

    def _parse_gametype_string(self, gametype_str: str) -> bool:
        """Parses the game type string to set the tournament category and limit type.

        This method analyzes the gametype string and updates the category and limit type accordingly.

        Args:
            gametype_str: The string containing game type information.

        Returns:
            bool: True if parsing and setting was successful, False otherwise.

        """
        if "holdem" in gametype_str:
            self.gametype["category"] = "holdem"
            return self._set_limit_type(gametype_str)
        if "omaha" in gametype_str:
            self.gametype["category"] = "5_omahahi" if "5" in gametype_str else "omahahi"
            return self._set_limit_type(gametype_str)
        return False

    def _set_limit_type(self, gametype_str: str) -> bool:
        """Sets the limit type for the tournament based on the gametype string.

        This method updates the limit type in the gametype dictionary according to the parsed game type string.

        Args:
            gametype_str: The string containing game type information.

        Returns:
            bool: True if a valid limit type was set, False otherwise.

        """
        if "no-limit" in gametype_str:
            self.gametype["limitType"] = "nl"
        elif "pot-limit" in gametype_str:
            self.gametype["limitType"] = "pl"
        elif "limit" in gametype_str:
            self.gametype["limitType"] = "fl"
        else:
            return False
        return True

    def _parse_basic_info(self, mg: dict) -> None:
        """Parses basic tournament information from the match group dictionary.

        This method extracts and sets entries, prizepool, start time, and tournament number from the parsed match group.

        Args:
            mg: Dictionary containing parsed match group data.

        """
        if "ENTRIES" in mg:
            self.entries = mg["ENTRIES"]
        if "PRIZEPOOL1" in mg and mg["PRIZEPOOL1"] is not None:
            self.prizepool = int(100 * self.convert_to_decimal(mg["PRIZEPOOL1"]))
        if "PRIZEPOOL2" in mg and mg["PRIZEPOOL2"] is not None:
            self.prizepool = int(100 * self.convert_to_decimal(mg["PRIZEPOOL2"]))
        if "DATETIME" in mg:
            self.startTime = datetime.datetime.strptime(
                mg["DATETIME"],
                "%Y/%m/%d %H:%M:%S UTC",
            ).replace(tzinfo=datetime.timezone.utc)
        if "TOURNO" in mg:
            self.tourNo = mg["TOURNO"]

    def _parse_buyin_info(self, mg: dict) -> None:
        """Parses buy-in and fee information from the match group dictionary.

        This method extracts and sets the buy-in amount, fee, and currency for the tournament,
        including handling special cases such as freerolls and KO bounties.

        Args:
            mg: Dictionary containing parsed match group data.

        """
        # Initialize with default currency, will be overridden by detection logic
        self.buyinCurrency = "EUR"
        self.currency = "EUR"

        if "BUYIN" not in mg:
            return

        if mg["BUYIN"] in ("Gratuit", "Freeroll", "Ticket uniquement", "Ticket"):
            self.buyin = 0
            self.fee = 0
            self.buyinCurrency = "FREE"
            self.currency = "FREE"
            return

        # Determine currency from buy-in text
        detected_currency = self._determine_currency(mg["BUYIN"])
        self.buyinCurrency = detected_currency
        self.currency = detected_currency

        # Handle KO bounty
        if mg["BIBOUNTY"] is not None and mg["BIRAKE"] is not None:
            self.koBounty = int(
                100 * Decimal(self.convert_to_decimal(mg["BIRAKE"].strip("\r"))),
            )
            self.isKO = True
            mg["BIRAKE"] = mg["BIBOUNTY"].strip("\r")

        rake = mg["BIRAKE"].strip("\r")
        self.buyin = int(100 * self.convert_to_decimal(mg["BIAMT"]))
        self.fee = int(100 * self.convert_to_decimal(rake))

        if self.buyin == 0 and self.fee == 0:
            self.buyinCurrency = "FREE"
            self.currency = "FREE"

    def _parse_rebuy_addon(self, mg: dict) -> None:
        """Parses rebuy and addon information from the match group dictionary.

        This method extracts and sets rebuy and addon costs for the tournament, including rake and fee calculations.

        Args:
            mg: Dictionary containing parsed match group data.

        """
        if "REBUY" in mg and mg["REBUY"] is not None:
            self.isRebuy = True
            rebuyrake = mg["REBUYRAKE"].strip("\r")
            rebuyamt = int(100 * self.convert_to_decimal(mg["REBUYAMT"]))
            rebuyfee = int(100 * self.convert_to_decimal(rebuyrake))
            self.rebuyCost = rebuyamt + rebuyfee

        if "ADDON" in mg and mg["ADDON"] is not None:
            self.isAddOn = True
            addonrake = mg["ADDONRAKE"].strip("\r")
            addonamt = int(100 * self.convert_to_decimal(mg["ADDONAMT"]))
            addonfee = int(100 * self.convert_to_decimal(addonrake))
            self.addOnCost = addonamt + addonfee

    def _parse_tournament_type(self, mg: dict) -> None:
        """Parses the tournament type and speed from the match group dictionary.

        This method determines if the tournament is a Sit & Go (SNG) and
        sets the speed attribute based on the parsed information.

        Args:
            mg: Dictionary containing parsed match group data.

        """
        sng_threshold = 10
        if int(self.entries) <= sng_threshold:  # TODO(@dev): obv not a great metric
            self.isSng = True
        if "MODE" in mg and mg["MODE"] is not None and "sng" in mg["MODE"]:
            self.isSng = True
        if "SPEED" in mg and mg["SPEED"] is not None:
            if mg["SPEED"] == "turbo":
                self.speed = "Hyper"
            elif mg["SPEED"] == "semiturbo":
                self.speed = "Turbo"

    def _determine_currency(self, amount_str: str) -> str:
        """Determine currency from amount string.

        Args:
            amount_str: String containing currency information

        Returns:
            str: Detected currency code (EUR, USD, GBP, CAD, WIFP, FREE, or play)
        """
        if not amount_str:
            return "EUR"  # Default fallback

        # Check for Euro symbols
        if "€" in amount_str or "EUR" in amount_str:
            return "EUR"
        # Check for Dollar symbols
        if "$" in amount_str or "USD" in amount_str:
            return "USD"
        # Check for Winamax points
        return "WIFP" if "FPP" in amount_str or "Free" in amount_str else "play"

    def _parse_player_info(self, mg: dict) -> None:
        """Parses player information from the match group dictionary.

        This method extracts and sets player name, rank, winnings, rebuy count, add-on count, and
        KO count from the parsed match group, and adds the player to the tournament summary.

        Args:
            mg: Dictionary containing parsed match group data.

        """
        if "PNAME" not in mg or mg["PNAME"] is None:
            return

        name = mg["PNAME"].strip("\r")
        rank = mg["RANK"]

        if rank == "...":
            return

        rank = int(mg["RANK"])
        winnings = 0
        rebuy_count = None
        add_on_count = None
        ko_count = None

        if "WINNINGS" in mg and mg["WINNINGS"] is not None:
            self.currency = self._determine_currency(mg["WINNINGS"])
            winnings = int(100 * self.convert_to_decimal(mg["WINNINGS"]))

        if "PREBUYS" in mg and mg["PREBUYS"] is not None:
            rebuy_count = int(mg["PREBUYS"])

        if "PADDONS" in mg and mg["PADDONS"] is not None:
            add_on_count = int(mg["PADDONS"])

        if "TICKET" in mg and mg["TICKET"] is not None:
            winnings += int(100 * self.convert_to_decimal(mg["TICKET"]))

        if "BOUNTY" in mg and mg["BOUNTY"] is not None:
            ko_count = 100 * self.convert_to_decimal(mg["BOUNTY"]) / Decimal(self.koBounty)
            if winnings == 0:
                self.currency = self._determine_currency(mg["BOUNTY"])

        self.addPlayer(
            rank,
            name,
            winnings,
            self.currency,
            rebuy_count,
            add_on_count,
            ko_count,
        )

    def parseSummaryFile(self) -> None:
        """Parses a Winamax tournament summary from a file.

        This method extracts all relevant tournament information from the summary text,
        including game type, basic info, buy-in, rebuy/addon, tournament type, and player info.
        It also detects if the tournament is an Expresso lottery tournament.

        """
        m = self.re_summary_tourney_info.search(self.summaryText)
        if m is None:
            tmp = self.summaryText[:200]
            log.error("parse Summary From File failed: '%s'", tmp)
            raise FpdbParseError

        mg = m.groupdict()

        self._parse_gametype(mg)
        self._parse_basic_info(mg)
        self._parse_buyin_info(mg)
        self._parse_rebuy_addon(mg)
        self._parse_tournament_type(mg)
        self._parse_player_info(mg)

        # Detect lottery tournaments after parsing
        self._detect_expresso_lottery()

    def convert_to_decimal(self, string: str) -> Decimal:
        """Converts a string representing a monetary value to a Decimal.

        This method cleans the input string and returns its value as a Decimal for precise calculations.

        Args:
            string: The string containing the monetary value.

        Returns:
            Decimal: The cleaned monetary value as a Decimal.

        """
        dec = self.clearMoneyString(string)
        return Decimal(dec)

    def _detect_expresso_lottery(self) -> None:
        """Detects if the tournament is an Expresso lottery tournament.

        This method checks the tournament name for 'Expresso' and sets the lottery flag and multiplier accordingly.

        """
        log.debug("Detecting Expresso lottery tournament")

        # Check if tournament name contains "Expresso"
        tournament_name = getattr(self, "tourneyName", "")
        if tournament_name and "Expresso" in tournament_name:
            self.isLottery = True
            log.info("Expresso lottery tournament detected: %s", tournament_name)

            # Calculate multiplier from prizepool vs buy-in total
            if hasattr(self, "prizepool") and hasattr(self, "buyin") and hasattr(self, "fee"):
                total_buyin = (self.buyin + self.fee) if self.buyin and self.fee else 0
                if total_buyin > 0 and self.prizepool > 0:
                    # Convert to same units (both should be in centimes)
                    multiplier = self.prizepool / total_buyin
                    self.tourneyMultiplier = round(multiplier)
                    log.info(
                        "Calculated multiplier: prizepool=%s, total_buyin=%s, multiplier=%sx",
                        self.prizepool,
                        total_buyin,
                        self.tourneyMultiplier,
                    )
                else:
                    self.tourneyMultiplier = 1
                    log.debug(
                        "Cannot calculate multiplier: prizepool=%s, buyin=%s, fee=%s",
                        getattr(self, "prizepool", None),
                        getattr(self, "buyin", None),
                        getattr(self, "fee", None),
                    )
            else:
                self.tourneyMultiplier = 1

            log.info("Lottery tournament: lottery=%s, multiplier=%s", self.isLottery, self.tourneyMultiplier)
        else:
            log.debug("Not an Expresso tournament: %s", tournament_name)
