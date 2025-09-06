"""iPoker tournament summary parser.

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
import decimal
import re
from decimal import Decimal
from typing import Any, ClassVar

from HandHistoryConverter import FpdbParseError
from loggingFpdb import get_logger
from TourneySummary import TourneySummary

log = get_logger("ipoker_summary_parser")


class iPokerSummary(TourneySummary):  # noqa: N801
    """iPoker tournament summary parser."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize iPokerSummary with default values for new fields."""
        super().__init__(*args, **kwargs)
        # Initialize new lottery fields with default values
        self.isLottery = False
        self.tourneyMultiplier = 1

    substitutions: ClassVar = {
        "LS": "\\$|\xe2\x82\xac|\xe2\u201a\xac|\u20ac|\xc2\xa3|\\£|RSD|kr|",
        "PLYR": r'(?P<PNAME>[^"]+)',
        "NUM": r".,0-9",
        "NUM2": r"\b((?:\d{1,3}(?:\s\d{3})*)|(?:\d+))\b",  # Regex pattern for matching numbers with spaces
    }
    currencies: ClassVar = {
        "€": "EUR",
        "$": "USD",
        "": "T$",
        "£": "GBP",
        "RSD": "RSD",
        "kr": "SEK",
    }

    months: ClassVar = {
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

    limits: ClassVar = {
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
    games: ClassVar = {
        "7 Card Stud": ("stud", "studhi"),
        "7 Card Stud Hi-Lo": ("stud", "studhilo"),
        "7 Card Stud HiLow": ("stud", "studhilo"),
        "5 Card Stud": ("stud", "5_studhi"),
        "Holdem": ("hold", "holdem"),
        "Six Plus Holdem": ("hold", "6_holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi-Lo": ("hold", "omahahilo"),
    }

    re_identify = re.compile(r"<game\sgamecode=")
    re_client = re.compile(r"<client_version>(?P<CLIENT>.*?)</client_version>")
    re_game_type = re.compile(
        r"""
            <gametype>(?P<GAME>((?P<CATEGORY>(5|7)\sCard\sStud(\sHi\-Lo)?(\sHiLow)?|(Six\sPlus\s)?Holdem|Omaha(\sHi\-Lo)?(\sHiLow)?)?\s?(?P<LIMIT>NL|SL|L|LZ|PL|БЛ|LP|No\slimit|Pot\slimit|Limit))|LH\s(?P<LSB>[{NUM}]+)({LS})?/(?P<LBB>[{NUM}]+)({LS})?.+?)
            (\s({LS})?(?P<SB>[{NUM}]+)({LS})?/({LS})?(?P<BB>[{NUM}]+))?({LS})?(\sAnte\s({LS})?(?P<ANTE>[{NUM}]+)({LS})?)?</gametype>\s+?
            <tablename>(?P<TABLE>.+)?</tablename>\s+?
            (<(tablecurrency|tournamentcurrency)>.*</(tablecurrency|tournamentcurrency)>\s+?)?
            (<smallblind>.+</smallblind>\s+?)?
            (<bigblind>.+</bigblind>\s+?)?
            <duration>.+</duration>\s+?
            <gamecount>.+</gamecount>\s+?
            <startdate>(?P<DATETIME>.+)</startdate>\s+?
            <currency>(?P<CURRENCY>.+)</currency>\s+?
            <nickname>(?P<HERO>.+)</nickname>
            """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_game_info_trny2 = re.compile(
        r"""
                        (?:(<tour(?:nament)?code>(?P<TOURNO>\d+)</tour(?:nament)?code>))|
                        (?:(<tournamentname>(?P<NAME>[^<]*)</tournamentname>))|
                        (?:(<place>(?P<PLACE>.+?)</place>))|
                        (?:(<buyin>(?P<BIAMT>[{NUM2}{LS}]+|\bToken\b)(?:\s\+\s)?(?P<BIRAKE>[{NUM2}{LS}]+)?)</buyin>)|
                        (?:(<totalbuyin>(?P<TOTBUYIN>[{NUM2}{LS}]+)</totalbuyin>))|
                        (?:(<win>({LS})?(?P<WIN>.+?|[{NUM2}{LS}]+)</win>))|
                        (?:(<rewarddrawn>(?P<REWARDDRAWN>[{NUM2}{LS}]+)</rewarddrawn>))
        """.format(**substitutions),
        re.VERBOSE,
    )

    re_buyin = re.compile(
        r"""(?P<BUYIN>[{NUM}]+)""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    re_tour_no = re.compile(r"(?P<TOURNO>\d+)$", re.MULTILINE)
    re_total_buyin = re.compile(
        r"""(?P<BUYIN>(?P<BIAMT>[{LS}{NUM}]+)\s\+\s?(?P<BIRAKE>[{LS}{NUM}]+)?)""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    re_date_time1 = re.compile(
        r"""(?P<D>[0-9]{2})\-(?P<M>[a-zA-Z]{3})\-(?P<Y>[0-9]{4})\s+(?P<H>[0-9]+):(?P<MIN>[0-9]+)(:(?P<S>[0-9]+))?""",
        re.MULTILINE,
    )
    re_date_time2 = re.compile(
        r"""(?P<D>[0-9]{2})[\/\.](?P<M>[0-9]{2})[\/\.](?P<Y>[0-9]{4})\s+(?P<H>[0-9]+):(?P<MIN>[0-9]+)(:(?P<S>[0-9]+))?""",
        re.MULTILINE,
    )
    re_date_time3 = re.compile(
        r"""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})\s+(?P<H>[0-9]+):(?P<MIN>[0-9]+)(:(?P<S>[0-9]+))?""",
        re.MULTILINE,
    )
    re_place = re.compile(
        r"""(<place>(?P<PLACE>.+?)</place>)""".format(),
        re.VERBOSE,
    )
    re_fpp = re.compile(r"Pts\s")

    # Add the non-decimal regex used to strip currency symbols/spaces:
    re_non_decimal = re.compile(r"[^\d.,]+")

    codepage: ClassVar = ["utf8", "cp1252"]

    def getSplitRe(self, _head: str) -> re.Pattern[str]:
        """Get regex pattern for splitting tournament summaries."""
        return re.compile(r"<session\ssessioncode=")

    def parseSummary(self) -> None:  # noqa: C901, PLR0912, PLR0915
        """Parse tournament summary text."""
        log.debug("Starting parseSummary.")
        m = self.re_game_type.search(self.summaryText)
        if not m:
            tmp = self.summaryText[0:200]
            log.error("determine GameType not found: '%s'", tmp)
            raise FpdbParseError
        log.debug("Found a match for GameType.")

        mg = m.groupdict()
        log.debug("GameType match groups: %s", mg)

        if "SB" in mg and mg["SB"] is not None:
            tmp = self.summaryText[0:200]
            log.error("Text does not appear to be a tournament: '%s'", tmp)
            raise FpdbParseError
        log.debug("No SB found, treating as tournament.")
        tourney = True
        log.info("Tournament flag set to true")

        if "GAME" in mg:
            if mg.get("CATEGORY") is None:
                self.info["base"], self.info["category"] = ("hold", "5_omahahi")
                log.debug("No CATEGORY found, defaulting to hold/5_omahahi.")
            else:
                self.gametype["base"], self.gametype["category"] = self.games[mg["CATEGORY"]]
                log.debug(
                    "Set base/category to: %s/%s",
                    self.gametype["base"],
                    self.gametype["category"],
                )

        if "LIMIT" in mg:
            self.gametype["limitType"] = self.limits[mg["LIMIT"]]
            log.debug("Set limitType to %s", self.gametype["limitType"])

        m2 = self.re_date_time1.search(mg["DATETIME"])
        if m2:
            month = self.months[m2.group("M")]
            sec = m2.group("S") or "00"
            datetimestr = f"{m2.group('Y')}/{month}/{m2.group('D')} {m2.group('H')}:{m2.group('MIN')}:{sec}"
            self.startTime = datetime.datetime.strptime(
                datetimestr,
                "%Y/%m/%d %H:%M:%S",
            ).replace(tzinfo=datetime.timezone.utc)
            log.debug("Parsed startTime with re_date_time1: %s", self.startTime)
        else:
            try:
                self.startTime = datetime.datetime.strptime(
                    mg["DATETIME"],
                    "%Y-%m-%d %H:%M:%S",
                ).replace(tzinfo=datetime.timezone.utc)
                log.debug("Parsed startTime with default format: %s", self.startTime)
            except ValueError:
                log.debug("Default format failed, trying alternative date formats.")
                date_match = self.re_date_time2.search(mg["DATETIME"])
                if date_match is not None:
                    datestr = "%d/%m/%Y %H:%M:%S" if "/" in mg["DATETIME"] else "%d.%m.%Y %H:%M:%S"
                    if date_match.group("S") is None:
                        datestr = "%d/%m/%Y %H:%M"
                else:
                    date_match1 = self.re_date_time3.search(mg["DATETIME"])
                    if date_match1 is None:
                        log.exception("Could not read datetime from the provided formats.")
                        raise FpdbParseError from None
                    datestr = "%Y/%m/%d %H:%M:%S"
                    if date_match1.group("S") is None:
                        datestr = "%Y/%m/%d %H:%M"
                self.startTime = datetime.datetime.strptime(
                    mg["DATETIME"],
                    datestr,
                ).replace(tzinfo=datetime.timezone.utc)
                log.debug("Parsed startTime with fallback format: %s", self.startTime)

        if not mg["CURRENCY"] or mg["CURRENCY"] == "fun":
            self.buyinCurrency = "play"
            log.debug("Currency is fun/play, setting buyinCurrency=play")
        else:
            self.buyinCurrency = mg["CURRENCY"]
            log.debug("Set buyinCurrency to %s", self.buyinCurrency)
        self.currency = self.buyinCurrency

        mt = self.re_tour_no.search(mg["TABLE"])
        if mt:
            self.tourNo = mt.group("TOURNO")
            log.debug("Extracted tourNo: %s", self.tourNo)
        else:
            tour_no = mg["TABLE"].split(",")[-1].strip().split(" ")[0]
            if tour_no.isdigit():
                self.tourNo = tour_no
                log.debug("Parsed tourNo from table string: %s", self.tourNo)
            else:
                log.debug(
                    "No numeric tourNo found in table string. TourNo may remain None.",
                )

        if tourney:
            log.info("Entering tournament processing section")
            log.debug("Processing tournament-specific logic using re_game_info_trny2.")
            matches = list(self.re_game_info_trny2.finditer(self.summaryText))
            log.debug("Number of matches found with re_game_info_trny2: %d", len(matches))

            # Expecting at least 6 matches: 0=TOURNO, 1=NAME, 2=PLACE, 3=BIAMT/BIRAKE, 4=TOTBUYIN, 5=WIN, 6=REWARDDRAWN
            min_matches = 6  # Keep at 6 since REWARDDRAWN is optional
            if len(matches) < min_matches:
                log.error(
                    "Not enough matches for tournament info: found %d, need at least %d.",
                    len(matches),
                    min_matches,
                )
                log.debug(
                    "Summary text snippet for debugging:\n%s",
                    self.summaryText[:500],
                )
                msg = "Not enough matches for tournament info."
                raise FpdbParseError(msg)

            for i, mat in enumerate(matches):
                log.debug("Match %d: %s", i, mat.groupdict())

            # Build mg2 dictionary from all matches
            mg2 = {
                "TOURNO": None,
                "NAME": None,
                "PLACE": None,
                "BIAMT": None,
                "BIRAKE": None,
                "TOTBUYIN": None,
                "WIN": None,
                "REWARDDRAWN": None,
            }

            # Extract data from each match
            for match in matches:
                groups = match.groupdict()
                mg2.update({key: value for key, value in groups.items() if value is not None})
            log.debug("Consolidated mg2: %s", mg2)

            self.buyin = 0
            self.fee = 0
            self.prizepool = None
            self.entries = None

            if mg2["TOURNO"]:
                self.tourNo = mg2["TOURNO"]
                log.debug("Confirmed tourNo: %s", self.tourNo)

            rank, winnings = None, None
            if mg2["PLACE"] and mg2["PLACE"] != "N/A":
                rank = int(mg2["PLACE"])
                log.debug("Extracted rank: %s", rank)
                if mg2["WIN"] and mg2["WIN"] != "N/A":
                    winnings = int(100 * self.convert_to_decimal(mg2["WIN"]))
                    log.debug("Calculated winnings: %s", winnings)

            self.tourneyName = mg2["NAME"]
            if self.tourNo and (" " + self.tourNo) in mg2["NAME"]:
                self.tourneyName = mg2["NAME"].replace(" " + self.tourNo, "")
            log.debug("Set tourneyName to %s", self.tourneyName)

            # Handle "Token" buyin scenario
            if mg2["BIAMT"] and mg2["BIAMT"].strip().lower() == "token":
                log.debug("Buy-in detected as Token. Attempting fallback to TOTBUYIN.")
                if mg2["TOTBUYIN"]:
                    stripped_tot = self.re_non_decimal.sub("", mg2["TOTBUYIN"])
                    if stripped_tot:
                        mg2["BIAMT"] = stripped_tot
                        mg2["BIRAKE"] = "0"
                        log.debug(
                            "Converted Token buy-in: BIAMT=%s and set BIRAKE=0.",
                            mg2["BIAMT"],
                        )
                    else:
                        log.debug(
                            "TOTBUYIN present but could not parse numeric value. Setting BIAMT=0.",
                        )
                        mg2["BIAMT"] = "0"
                        mg2["BIRAKE"] = "0"
                else:
                    log.debug(
                        "Token buyin but no TOTBUYIN available. Setting default buyin=0, fee=0.",
                    )
                    mg2["BIAMT"] = "0"
                    mg2["BIRAKE"] = "0"

            if not mg2["BIRAKE"] and mg2["TOTBUYIN"]:
                log.debug("No BIRAKE found, trying to parse TOTBUYIN.")
                m3 = self.re_total_buyin.search(mg2["TOTBUYIN"])
                if m3:
                    mg2.update(m3.groupdict())
                    log.debug("Updated mg2 with total buyin info: %s", mg2)
                elif mg2.get("BIAMT"):
                    mg2["BIRAKE"] = "0"
                    log.debug(
                        "Set BIRAKE=0 due to missing explicit rake info, but BIAMT is present.",
                    )

            if mg2.get("BIAMT") and mg2.get("BIRAKE"):
                try:
                    self.buyin = int(100 * self.convert_to_decimal(mg2["BIAMT"]))
                except (ValueError, TypeError):
                    log.debug(
                        "Failed to parse BIAMT='%s', setting buyin=0.",
                        mg2["BIAMT"],
                    )
                    self.buyin = 0
                try:
                    self.fee = int(100 * self.convert_to_decimal(mg2["BIRAKE"]))
                except (ValueError, TypeError):
                    log.debug(
                        "Failed to parse BIRAKE='%s', setting fee=0.",
                        mg2["BIRAKE"],
                    )
                    self.fee = 0
                log.debug("Set buyin=%s, fee=%s", self.buyin, self.fee)

                if self.re_fpp.match(mg2["BIAMT"]):
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
            log.debug("Added hero player: %s, rank=%s, winnings=%s", hero, rank, winnings)

            # Detect Twister tournaments and calculate multiplier
            log.debug("Calling _detect_twister_tournament with mg2: %s", mg2)
            self._detect_twister_tournament(mg2)

            if self.tourNo is None:
                log.error("Could Not Parse tourNo")
                msg = "Could Not Parse tourNo"
                raise FpdbParseError(msg)

        else:
            tmp = self.summaryText[0:200]
            log.error("Text does not appear to be a tournament '%s'", tmp)
            raise FpdbParseError

        log.debug("Finished parseSummary successfully.")

    def _detect_twister_tournament(self, mg2: dict) -> None:
        """Detect Twister tournament and set lottery fields."""
        log.debug("Entering _detect_twister_tournament")
        try:
            # Check if this is a Twister tournament
            tournament_name = mg2.get("NAME", "")
            log.debug("Tournament name: '%s'", tournament_name)
            if "Twister" in tournament_name or "twister" in tournament_name.lower():
                log.debug("Detected Twister tournament from name: %s", tournament_name)

                # Extract rewarddrawn and calculate multiplier
                rewarddrawn_str = mg2.get("REWARDDRAWN", "")
                buyin_str = mg2.get("TOTBUYIN", "") or mg2.get("BIAMT", "")

                if rewarddrawn_str and buyin_str:
                    try:
                        rewarddrawn = self.convert_to_decimal(rewarddrawn_str)
                        buyin = self.convert_to_decimal(buyin_str)

                        if rewarddrawn > 0 and buyin > 0:
                            multiplier = rewarddrawn / buyin
                            if multiplier > 1:
                                self.isLottery = True
                                self.tourneyMultiplier = int(multiplier)
                                log.info(
                                    "Twister detected: lottery=%s, multiplier=%s (rewarddrawn=%s, buyin=%s)",
                                    self.isLottery,
                                    self.tourneyMultiplier,
                                    rewarddrawn,
                                    buyin,
                                )
                            else:
                                log.debug("Multiplier <= 1, not a lottery: %s", multiplier)
                        else:
                            log.debug(
                                "Invalid amounts for multiplier calculation: rewarddrawn=%s, buyin=%s",
                                rewarddrawn,
                                buyin,
                            )
                    except (ValueError, TypeError, decimal.InvalidOperation) as e:
                        log.debug("Error calculating Twister multiplier: %s", e)
                else:
                    log.debug("Missing rewarddrawn or buyin for Twister detection")
            else:
                log.debug("Not a Twister tournament (tournament name: %s)", tournament_name)
        except (ValueError, TypeError, decimal.InvalidOperation) as e:
            log.debug("Error in Twister detection: %s", e)

    def convert_to_decimal(self, string: str) -> Decimal:
        """Convert money string to decimal."""
        if not string:
            return Decimal(0)

        # Handle complex format with multiple amounts (e.g., "0€ + 0,02€ + 0,23€")
        if "+" in string:
            parts = string.split("+")
            total = Decimal(0)
            for part_str in parts:
                part = part_str.strip()
                if part:
                    # Use clearMoneyString to clean each part
                    cleaned = self.clearMoneyString(part)
                    # Replace comma with dot for decimal separator
                    cleaned = cleaned.replace(",", ".")
                    if cleaned:
                        try:
                            total += Decimal(cleaned)
                        except (ValueError, TypeError, decimal.InvalidOperation):
                            continue
            log.debug("Converted complex string '%s' to decimal %s", string, total)
            return total
        # Original logic for simple amounts
        dec = self.clearMoneyString(string)
        log.debug("Attempting to convert string to decimal: '%s' => '%s'", string, dec)
        if not dec:
            log.debug("Empty string after cleaning, returning 0.")
            return Decimal(0)
        m = self.re_buyin.search(dec)
        if m:
            try:
                dec = Decimal(m.group("BUYIN"))
                log.debug("Converted string '%s' to decimal %s", string, dec)
            except (ValueError, TypeError, decimal.InvalidOperation) as e:
                log.debug(
                    "Failed to convert '%s' to decimal: %s, defaulting to 0.",
                    string,
                    e,
                )
                dec = Decimal(0)
        else:
            log.debug(
                "No numeric buyin match found in string '%s', defaulting to 0.",
                string,
            )
            dec = Decimal(0)
        return dec
