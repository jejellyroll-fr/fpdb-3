from __future__ import annotations

import decimal
import re
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("ipoker_parser")


class IPokerXMLFormatMixin:
    """XML-format game type parsing for iPoker hand histories."""

    whole_file: str
    info: dict[str, Any]
    tinfo: dict[str, Any]
    tablename: str
    hero: str

    if TYPE_CHECKING:

        def _filename_game_info_source(self) -> str: ...

    def _parse_xml_format(self, hand_text: str) -> dict | None:  # noqa: ARG002, PLR0912, PLR0915, C901
        """Parse XML format by combining session and game level information."""
        log.debug("Parsing XML format")

        # Extract session-level info from whole_file
        session_patterns = {
            "gametype": r"<gametype>([^<]*)</gametype>",
            "tablename": r"<tablename>([^<]*)</tablename>",
            "currency": r"<currency>([^<]*)</currency>",
            "nickname": r"<nickname>([^<]*)</nickname>",
        }

        session_info: dict[str, str] = {}
        for key, pattern in session_patterns.items():
            match = re.search(pattern, self.whole_file)
            if match:
                session_info[key] = match.group(1)
                log.debug("Found session %s: %s", key, match.group(1))

        # Check if we have the minimum required info
        if "gametype" not in session_info:
            log.debug("No gametype found in session info")
            return None

        # Parse the gametype string to extract game information
        gametype_text = session_info["gametype"]
        log.debug("Parsing gametype: %s", gametype_text)

        # Initialize info directly from XML data
        self.info = {}

        # Parse gametype string - handle both formats
        gametype_pattern_with_blinds = (
            r"(\w+(?:\s+\w+)*)\s+" r"(NL|PL|L|SL|БЛ|LP|No\s+limit|Pot\s+limit|Limit)\s*" r"[^\d]*([0-9.,]+)/[^\d]*([0-9.,]+)"
        )
        gametype_pattern_no_blinds = r"(\w+(?:\s+\w+)*)\s+" r"(NL|PL|L|SL|БЛ|LP|No\s+limit|Pot\s+limit|Limit)\s*$"

        gametype_match = re.match(gametype_pattern_with_blinds, gametype_text)
        if not gametype_match:
            gametype_match = re.match(gametype_pattern_no_blinds, gametype_text)

        if gametype_match:
            game_name = gametype_match.group(1)
            limit_type = gametype_match.group(2)

            # Set game category
            if "Holdem" in game_name or "Hold" in game_name:
                self.info["base"] = "hold"
                self.info["category"] = "holdem"
            elif "Omaha" in game_name:
                self.info["base"] = "hold"
                if "Hi-Lo" in game_name or "HiLow" in game_name:
                    self.info["category"] = "omahahilo"
                else:
                    self.info["category"] = "omahahi"
            elif "Stud" in game_name:
                self.info["base"] = "stud"
                if "Hi-Lo" in game_name or "HiLow" in game_name:
                    self.info["category"] = "studhilo"
                else:
                    self.info["category"] = "studhi"

            # Set limit type
            if limit_type in ("NL", "No limit", "SL", "БЛ"):
                self.info["limitType"] = "nl"
            elif limit_type in ("PL", "Pot limit", "LP"):
                self.info["limitType"] = "pl"
            elif limit_type in ("L", "Limit"):
                self.info["limitType"] = "fl"

            # Set blinds if present, otherwise use defaults
            min_groups_for_blinds = 4
            if len(gametype_match.groups()) >= min_groups_for_blinds:
                # Has blinds info
                sb = gametype_match.group(3)
                bb = gametype_match.group(4)
                self.info["sb"] = sb.replace(",", ".")
                self.info["bb"] = bb.replace(",", ".")
            elif self.info.get("base") == "stud":
                # For stud tournaments, use ante-based structure
                self.info["sb"] = "0"
                self.info["bb"] = "0"
            else:
                # For hold'em/omaha tournaments, use default blind structure
                self.info["sb"] = "10"
                self.info["bb"] = "20"
        else:
            # If regex doesn't match, try to extract game info from filename or fallback
            log.debug("Gametype regex failed, trying fallback parsing")

            # Try to extract from filename if available
            filename = self._filename_game_info_source()
            log.debug("Extracting game info from filename: %s", filename)

            # Set defaults
            self.info["base"] = "hold"
            self.info["category"] = "holdem"
            self.info["limitType"] = "nl"
            self.info["sb"] = "0.01"
            self.info["bb"] = "0.02"

            # Parse from filename patterns
            if "7-Stud" in filename or "Stud" in filename:
                self.info["base"] = "stud"
                if "HL" in filename or "Hi-Lo" in filename:
                    self.info["category"] = "studhilo"
                else:
                    self.info["category"] = "studhi"
            elif "PLO" in filename or "Omaha" in filename:
                self.info["base"] = "hold"
                if "HL" in filename or "Hi-Lo" in filename:
                    self.info["category"] = "omahahilo"
                else:
                    self.info["category"] = "omahahi"
            elif "NLHE" in filename or "Holdem" in filename:
                self.info["base"] = "hold"
                self.info["category"] = "holdem"

            # Extract limit type from filename
            if "LHE" in filename or filename.startswith("LHE"):
                self.info["limitType"] = "fl"
            elif "PLO" in filename or filename.startswith("PLO"):
                self.info["limitType"] = "pl"
            elif "NLHE" in filename or filename.startswith("NLHE"):
                self.info["limitType"] = "nl"
            elif "7-Stud" in filename and "L-" in filename:
                self.info["limitType"] = "fl"

            # Try to extract blinds from filename (e.g., "0.05-0.10")
            blind_match = re.search(r"([0-9.]+)-([0-9.]+)", filename)
            if blind_match:
                self.info["sb"] = blind_match.group(1)
                self.info["bb"] = blind_match.group(2)

            # Also try gametype text
            if "Omaha" in gametype_text:
                self.info["base"] = "hold"
                self.info["category"] = "omahahi"
            elif "Stud" in gametype_text:
                self.info["base"] = "stud"
                self.info["category"] = "studhi"
            elif "Holdem" in gametype_text or "Hold" in gametype_text:
                self.info["base"] = "hold"
                self.info["category"] = "holdem"

        # Detect tournament vs ring game
        if "<tournamentname>" in self.whole_file or "<place>" in self.whole_file:
            log.debug("Tournament detected in XML - setting type to tour")
            self.info["type"] = "tour"
            self.info["currency"] = "T$"  # Tournament currency

            # Initialize tournament info for XML format
            self.tinfo = {}
            self._initialize_xml_tournament_info()
        else:
            log.debug("No tournament markers found - setting type to ring")
            self.info["type"] = "ring"
            self.info["currency"] = session_info.get("currency", "USD")
        self.tablename = session_info.get("tablename", "Unknown")

        # Set hero from nickname
        if "nickname" in session_info:
            self.hero = session_info["nickname"]
            log.debug("Set hero from XML nickname: %s", self.hero)

        # Set defaults
        self.info["ante"] = 0
        self.info["buyinType"] = "regular"
        self.info["fast"] = False
        self.info["newToGame"] = False
        self.info["homeGame"] = False
        self.info["split"] = False
        self.info["mix"] = "none"

        log.debug("Final XML parsed info: %s", self.info)
        return self.info

    def _clean_currency_amount(self, amount_str: str) -> str:
        """Clean currency amount string for parsing.

        Handles European format (comma as decimal separator) and removes currency symbols.
        Also handles complex formats like '0€ + 0,02€ + 0,23€'.
        Example: '0,25€' -> '0.25'
        Example: '0€ + 0,02€ + 0,23€' -> '0.25'
        """
        if not amount_str:
            return "0"

        # Handle complex format with multiple amounts (e.g., "0€ + 0,02€ + 0,23€")
        if "+" in amount_str:
            parts = amount_str.split("+")
            total = Decimal(0)
            for part_str in parts:
                part = part_str.strip()
                if part:
                    # Remove currency symbols
                    cleaned = re.sub(r"[€$£¥]", "", part)
                    # Replace comma with dot for decimal separator
                    cleaned = cleaned.replace(",", ".")
                    # Remove any remaining non-digit, non-dot characters
                    cleaned = re.sub(r"[^\d.]", "", cleaned)
                    if cleaned:
                        try:
                            total += Decimal(cleaned)
                        except decimal.InvalidOperation:
                            continue
            return str(total)
        # Simple format
        # Remove currency symbols
        cleaned = re.sub(r"[€$£¥]", "", amount_str)

        # Replace comma with dot for decimal separator (European format)
        cleaned = cleaned.replace(",", ".")

        # Remove any remaining non-digit, non-dot characters
        cleaned = re.sub(r"[^\d.]", "", cleaned)

        # Handle empty string
        if not cleaned:
            return "0"

        return cleaned

    def _initialize_xml_tournament_info(self) -> None:  # noqa: C901, PLR0912, PLR0915
        """Initialize tournament info for XML format tournaments."""
        log.debug("Initializing tournament info for XML format")

        # Extract tournament info from whole_file - includes both old and new XML formats
        tourney_patterns = {
            # Basic tournament data
            "tournamentcode": r"<tournamentcode>([^<]*)</tournamentcode>",
            "tournamentname": r"<tournamentname>([^<]*)</tournamentname>",
            "place": r"<place>([^<]*)</place>",
            "buyin": r"<buyin>([^<]*)</buyin>",
            "birake": r"<birake>([^<]*)</birake>",
            "totalbuyin": r"<totalbuyin>([^<]*)</totalbuyin>",
            "win": r"<win>([^<]*)</win>",
            "currency": r"<currency>([^<]*)</currency>",
            "nickname": r"<nickname>([^<]*)</nickname>",
            # Extended tournament data
            "client_version": r"<client_version>([^<]*)</client_version>",
            "mode": r"<mode>([^<]*)</mode>",
            "duration": r"<duration>([^<]*)</duration>",
            "gamecount": r"<gamecount>([^<]*)</gamecount>",
            "rewarddrawn": r"<rewarddrawn>([^<]*)</rewarddrawn>",
            "statuspoints": r"<statuspoints>([^<]*)</statuspoints>",
            "awardpoints": r"<awardpoints>([^<]*)</awardpoints>",
            "ipoints": r"<ipoints>([^<]*)</ipoints>",
            "tablesize": r"<tablesize>([^<]*)</tablesize>",
            # Player performance data
            "bets": r"<bets>([^<]*)</bets>",
            "wins": r"<wins>([^<]*)</wins>",
            "chipsin": r"<chipsin>([^<]*)</chipsin>",
            "chipsout": r"<chipsout>([^<]*)</chipsout>",
            # Timing data
            "startdate": r"<startdate>([^<]*)</startdate>",
            "enddate": r"<enddate>([^<]*)</enddate>",
            # Game type data
            "gametype": r"<gametype>([^<]*)</gametype>",
            "tablename": r"<tablename>([^<]*)</tablename>",
        }

        tourney_info: dict[str, str] = {}
        for key, pattern in tourney_patterns.items():
            match = re.search(pattern, self.whole_file)
            if match:
                tourney_info[key] = match.group(1)
                log.debug("Found tournament %s: %s", key, match.group(1))

        # Initialize tinfo if not exists
        if not hasattr(self, "tinfo"):
            self.tinfo = {}

        # Extract tournament number - prefer tournamentcode over tablename parsing
        if tourney_info.get("tournamentcode"):
            self.tinfo["tourNo"] = tourney_info["tournamentcode"]
            log.debug("Using tournamentcode as tourNo: %s", self.tinfo["tourNo"])
        else:
            # Fallback: extract from tablename
            tablename = re.search(r"<tablename>([^<]*)</tablename>", self.whole_file)
            if tablename:
                tourno_match = re.search(r"(\d{9,})", tablename.group(1))
                if tourno_match:
                    self.tinfo["tourNo"] = tourno_match.group(1)
                    log.debug("Extracted tourNo from tablename: %s", self.tinfo["tourNo"])
                else:
                    self.tinfo["tourNo"] = "1"
                    log.debug("No tourNo found in tablename, using placeholder: 1")
            else:
                self.tinfo["tourNo"] = "1"
                log.debug("No tablename found, using placeholder tourNo: 1")

        # Set tournament info
        self.tinfo["tourName"] = tourney_info.get("tournamentname", "Unknown Tournament")

        # Parse buyin info - handle both old and new formats
        buyin_str = tourney_info.get("buyin", "0")
        birake_str = tourney_info.get("birake", "0")
        totalbuyin_str = tourney_info.get("totalbuyin", "0")

        # Parse amounts using European decimal format (comma as decimal separator)
        try:
            if buyin_str and buyin_str != "0":
                # Handle old format like "$0.22+$0.03" or new format like "0,22€"
                if "+" in buyin_str:
                    # Old format: "$0.22+$0.03"
                    parts = buyin_str.split("+")
                    min_parts = 2
                    if len(parts) >= min_parts:
                        buyin_clean = self._clean_currency_amount(parts[0])
                        fee_clean = self._clean_currency_amount(parts[1])
                        self.tinfo["buyin"] = int(Decimal(buyin_clean) * 100)
                        self.tinfo["fee"] = int(Decimal(fee_clean) * 100)
                    else:
                        buyin_clean = self._clean_currency_amount(buyin_str)
                        self.tinfo["buyin"] = int(Decimal(buyin_clean) * 100)
                        self.tinfo["fee"] = 0
                else:
                    # New format: "0,22€"
                    buyin_clean = self._clean_currency_amount(buyin_str)
                    self.tinfo["buyin"] = int(Decimal(buyin_clean) * 100)
                    self.tinfo["fee"] = 0
            else:
                self.tinfo["buyin"] = 0
                self.tinfo["fee"] = 0

            # Handle separate fee (birake) field
            if birake_str and birake_str != "0":
                birake_clean = self._clean_currency_amount(birake_str)
                self.tinfo["fee"] = int(Decimal(birake_clean) * 100)

            # If no buyin/fee but totalbuyin exists, use totalbuyin as buyin
            if self.tinfo["buyin"] == 0 and self.tinfo["fee"] == 0 and totalbuyin_str and totalbuyin_str != "0":
                totalbuyin_clean = self._clean_currency_amount(totalbuyin_str)
                self.tinfo["buyin"] = int(Decimal(totalbuyin_clean) * 100)
                self.tinfo["fee"] = 0
                log.debug("Using totalbuyin as buyin: %s", self.tinfo["buyin"])

        except (ValueError, TypeError, decimal.InvalidOperation) as e:
            log.warning("Error parsing buyin amounts: %s", e)
            self.tinfo["buyin"] = 0
            self.tinfo["fee"] = 0

        # Set currency
        self.tinfo["currency"] = tourney_info.get("currency", "EUR")
        self.tinfo["buyinCurrency"] = self.tinfo["currency"]

        if self.tinfo["buyin"] == 0:
            self.tinfo["buyinCurrency"] = "FREE"

        # Set hero (player nickname)
        if tourney_info.get("nickname"):
            self.tinfo["hero"] = tourney_info["nickname"]

        # Extended tournament data
        self.tinfo["client_version"] = tourney_info.get("client_version", "")
        self.tinfo["mode"] = tourney_info.get("mode", "")
        self.tinfo["duration"] = tourney_info.get("duration", "")
        self.tinfo["gamecount"] = tourney_info.get("gamecount", "0")
        self.tinfo["tablesize"] = tourney_info.get("tablesize", "")

        # iPoker points and rewards
        self.tinfo["statuspoints"] = tourney_info.get("statuspoints", "0")
        self.tinfo["awardpoints"] = tourney_info.get("awardpoints", "0")
        self.tinfo["ipoints"] = tourney_info.get("ipoints", "0")

        # Reward drawn (prize pool amount for Twister lottery)
        if tourney_info.get("rewarddrawn"):
            try:
                reward_clean = self._clean_currency_amount(tourney_info["rewarddrawn"])
                self.tinfo["rewarddrawn"] = Decimal(reward_clean)
                self.tinfo["rewarddrawn_cents"] = int(self.tinfo["rewarddrawn"] * 100)
            except (ValueError, TypeError, decimal.InvalidOperation):
                self.tinfo["rewarddrawn"] = Decimal(0)
                self.tinfo["rewarddrawn_cents"] = 0
        else:
            self.tinfo["rewarddrawn"] = Decimal(0)
            self.tinfo["rewarddrawn_cents"] = 0

        # Calculate Twister multiplier (rewarddrawn / buyin)
        if self.tinfo["rewarddrawn"] > 0 and self.tinfo["buyin"] > 0:
            # Convert buyin from cents to euros for calculation
            buyin_euros = Decimal(self.tinfo["buyin"]) / 100
            self.tinfo["multiplier"] = self.tinfo["rewarddrawn"] / buyin_euros
            log.debug(
                "Calculated Twister multiplier: %s (rewarddrawn: %s / buyin: %s)",
                self.tinfo["multiplier"],
                self.tinfo["rewarddrawn"],
                buyin_euros,
            )
        else:
            self.tinfo["multiplier"] = Decimal(0)
            log.debug(
                "Cannot calculate multiplier: rewarddrawn=%s, buyin=%s",
                self.tinfo["rewarddrawn"],
                self.tinfo["buyin"],
            )

        # Player performance data
        self.tinfo["bets"] = tourney_info.get("bets", "0")
        self.tinfo["wins"] = tourney_info.get("wins", "0")
        self.tinfo["chipsin"] = tourney_info.get("chipsin", "0")
        self.tinfo["chipsout"] = tourney_info.get("chipsout", "0")

        # Parse hero winnings
        if tourney_info.get("win"):
            try:
                win_clean = self._clean_currency_amount(tourney_info["win"])
                self.tinfo["hero_winnings"] = Decimal(win_clean)
                self.tinfo["hero_winnings_cents"] = int(self.tinfo["hero_winnings"] * 100)
            except (ValueError, TypeError, decimal.InvalidOperation):
                self.tinfo["hero_winnings"] = Decimal(0)
                self.tinfo["hero_winnings_cents"] = 0
        else:
            self.tinfo["hero_winnings"] = Decimal(0)
            self.tinfo["hero_winnings_cents"] = 0

        # Parse timing data
        if tourney_info.get("startdate"):
            try:
                import datetime as dt

                start_time = dt.datetime.strptime(tourney_info["startdate"], "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
                self.tinfo["startTime"] = start_time.replace(tzinfo=dt.timezone.utc)
            except (ValueError, TypeError):
                self.tinfo["startTime"] = None

        if tourney_info.get("enddate"):
            try:
                import datetime as dt

                end_time = dt.datetime.strptime(tourney_info["enddate"], "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
                self.tinfo["endTime"] = end_time.replace(tzinfo=dt.timezone.utc)
            except (ValueError, TypeError):
                self.tinfo["endTime"] = None

        # Set table name for tournament
        self.tablename = "1"
        self.info["table_name"] = self.tinfo["tourName"]

        log.debug("Initialized tournament info: %s", self.tinfo)
