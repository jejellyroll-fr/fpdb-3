"""iPoker hand history converter for FPDB.

This module provides functionality to parse iPoker network hand histories
and convert them to FPDB format, including support for multiple skins.
"""
#
#    Copyright 2010-2012, Carl Gherardi
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

########################################################################

# This code is based on CarbonToFpdb.py by Matthew Boss
#
# TODO(@author): Implement missing features:
#
# -- No support for tournaments (see also the last item below)
# -- Assumes that the currency of ring games is USD
# -- No support for a bring-in or for antes (is the latter in fact unnecessary
#    for hold 'em on Carbon?)
# -- hand.maxseats can only be guessed at
# -- The last hand in a history file will often be incomplete and is therefore
#    rejected
# -- Is behaviour currently correct when someone shows an uncalled hand?
# -- Information may be lost when the hand ID is converted from the native form
#    handid-yyy(y*) to handidyyy(y*) (in principle this should be stored as
#    a string, but the database does not support this). Is there a possibility
#    of collision between hand IDs that ought to be distinct?
# -- Cannot parse tables that run it twice (nor is this likely ever to be
#    possible)
# -- Cannot parse hands in which someone is all in in one of the blinds. Until
#    this is corrected tournaments will be unparseable

import datetime
import decimal
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

import Database
from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger
from TourneySummary import TourneySummary

log = get_logger("parser")


class iPoker(HandHistoryConverter):  # noqa: N801
    """A class for converting iPoker hand history files to the PokerTH format."""

    # Constants
    DECIMAL_PARTS_COUNT = 2
    MIN_CLIENT_VERSION_FOR_UNCALLED_BETS = 20
    MIN_TOURNAMENT_MATCHES_REQUIRED = 6
    THIRD_STREET_CARDS_COUNT = 3
    SECOND_STREET_CARDS_COUNT = 2

    sitename = "iPoker"
    filetype = "text"
    codepage = ("utf8", "cp1252")
    site_id = 14
    copy_game_header = True  # NOTE: Not sure if this is necessary yet. The file is xml so its likely
    summary_in_file = False
    summary_in_file_alt = False  # Alternative naming used by importer

    substitutions: ClassVar[dict[str, str]] = {
        "LS": r"\$|\xe2\x82\xac|\xe2\u201a\xac|\u20ac|\xc2\xa3|\£|RSD|kr|",  # Currency symbols
        "PLYR": r"(?P<PNAME>[^\"]+)",  # Regex pattern for matching player names
        "NUM": r"(.,\d+)|(\d+)",  # Regex pattern for matching numbers
        "NUM2": r"\b((?:\d{1,3}(?:\s\d{3})*)|(?:\d+))\b",  # Regex pattern for matching numbers with spaces
    }

    limits: ClassVar[dict[str, str]] = {
        "No limit": "nl",
        "Pot limit": "pl",
        "Limit": "fl",
        "NL": "nl",
        "SL": "nl",
        "БЛ": "nl",
        "PL": "pl",
        "LP": "pl",
        "L": "fl",
        "LZ": "nl",
    }
    games: ClassVar[dict[str, tuple[str, str]]] = {  # base, category
        "7 Card Stud": ("stud", "studhi"),
        "7 Card Stud Hi-Lo": ("stud", "studhilo"),
        "7 Card Stud HiLow": ("stud", "studhilo"),
        "5 Card Stud": ("stud", "5_studhi"),
        "Holdem": ("hold", "holdem"),
        "Six Plus Holdem": ("hold", "6_holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi-Lo": ("hold", "omahahilo"),
        "Omaha HiLow": ("hold", "omahahilo"),
    }

    currencies: ClassVar[dict[str, str]] = {
        "€": "EUR",
        "$": "USD",
        "": "T$",
        "£": "GBP",
        "RSD": "RSD",
        "kr": "SEK",
    }

    # translations from captured groups to fpdb info strings
    Lim_Blinds: ClassVar[dict[str, tuple[str, str]]] = {
        "0.04": ("0.01", "0.02"),
        "0.08": ("0.02", "0.04"),
        "0.10": ("0.02", "0.05"),
        "0.20": ("0.05", "0.10"),
        "0.40": ("0.10", "0.20"),
        "0.50": ("0.10", "0.25"),
        "1.00": ("0.25", "0.50"),
        "1": ("0.25", "0.50"),
        "2.00": ("0.50", "1.00"),
        "2": ("0.50", "1.00"),
        "4.00": ("1.00", "2.00"),
        "4": ("1.00", "2.00"),
        "6.00": ("1.00", "3.00"),
        "6": ("1.00", "3.00"),
        "8.00": ("2.00", "4.00"),
        "8": ("2.00", "4.00"),
        "10.00": ("2.00", "5.00"),
        "10": ("2.00", "5.00"),
        "20.00": ("5.00", "10.00"),
        "20": ("5.00", "10.00"),
        "30.00": ("10.00", "15.00"),
        "30": ("10.00", "15.00"),
        "40.00": ("10.00", "20.00"),
        "40": ("10.00", "20.00"),
        "60.00": ("15.00", "30.00"),
        "60": ("15.00", "30.00"),
        "80.00": ("20.00", "40.00"),
        "80": ("20.00", "40.00"),
        "100.00": ("25.00", "50.00"),
        "100": ("25.00", "50.00"),
        "150.00": ("50.00", "75.00"),
        "150": ("50.00", "75.00"),
        "200.00": ("50.00", "100.00"),
        "200": ("50.00", "100.00"),
        "400.00": ("100.00", "200.00"),
        "400": ("100.00", "200.00"),
        "800.00": ("200.00", "400.00"),
        "800": ("200.00", "400.00"),
        "1000.00": ("250.00", "500.00"),
        "1000": ("250.00", "500.00"),
        "2000.00": ("500.00", "1000.00"),
        "2000": ("500.00", "1000.00"),
    }

    months: ClassVar[dict[str, int]] = {
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

    # Static regexes
    re_client = re.compile(r"<client_version>(?P<CLIENT>.*?)</client_version>")
    re_identify = re.compile("""<game gamecode=\"\\d+\">""")
    re_split_hands = re.compile(r"</game>")
    re_tail_split_hands = re.compile(r"(</game>)")
    re_game_info = re.compile(
        r"""
            <gametype>(?P<GAME>((?P<CATEGORY>(5|7)\sCard\sStud(\sHi\-Lo|\sHiLow)?|(Six\sPlus\s)?Holdem|Omaha(\sHi\-Lo|\sHiLow)?)?\s?(?P<LIMIT>NL|SL|L|LZ|PL|БЛ|LP|No\slimit|Pot\slimit|Limit))|LH\s(?P<LSB>[{NUM}]+)({LS})?/(?P<LBB>[{NUM}]+)({LS})?.+?)
            (\s({LS})?(?P<SB>[{NUM}]+)({LS})?/({LS})?(?P<BB>[{NUM}]+))?({LS})?(\sAnte\s({LS})?(?P<ANTE>[{NUM}]+)({LS})?)?</gametype>\s+?
            <tablename>(?P<TABLE>.+)?</tablename>\s+?
            (<(tablecurrency|tournamentcurrency)>(?P<TABLECURRENCY>.*)</(tablecurrency|tournamentcurrency)>\s+?)?
            (<smallblind>.+</smallblind>\s+?)?
            (<bigblind>.+</bigblind>\s+?)?
            (<duration>.+</duration>\s+?)?
            (<gamecount>.+</gamecount>\s+?)?
            (<startdate>.+</startdate>\s+?)?
            <currency>(?P<CURRENCY>.+)?</currency>\s+?
            <nickname>(?P<HERO>.+)?</nickname>
            """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    re_game_info_trny = re.compile(
        r"""
                        (?:(<tour(?:nament)?code>(?P<TOURNO>\d+)</tour(?:nament)?code>))|
                        (?:(<tournamentname>(?P<NAME>[^<]*)</tournamentname>))|
                        (?:(<rewarddrawn>(?P<REWARD>[{NUM2}{LS}]+)</rewarddrawn>))|
                        (?:(<place>(?P<PLACE>.+?)</place>))|
                        (?:(<buyin>(?P<BIAMT>[{NUM2}{LS}]+)\s\+\s)?(?P<BIRAKE>[{NUM2}{LS}]+)\s\+\s(?P<BIRAKE2>[{NUM2}{LS}]+)</buyin>)|
                        (?:(<totalbuyin>(?P<TOTBUYIN>.*)</totalbuyin>))|
                        (?:(<win>({LS})?(?P<WIN>.+?|[{NUM2}{LS}]+)</win>))
                        """.format(**substitutions),
        re.VERBOSE,
    )

    re_game_info_trny2 = re.compile(
        r"""
            (?:(<tour(?:nament)?code>(?P<TOURNO>\d+)</tour(?:nament)?code>))|
            (?:(<tournamentname>(?P<NAME>[^<]*)</tournamentname>))|
            (?:(<place>(?P<PLACE>.+?)</place>))|
            (?:(<buyin>(?P<BIAMT>[{NUM2}{LS}]+)\s\+\s)?(?P<BIRAKE>[{NUM2}{LS}]+)\s\+\s(?P<BIRAKE2>[{NUM2}{LS}]+)</buyin>)|
            (?:(<totalbuyin>(?P<TOTBUYIN>[{NUM2}{LS}]+)</totalbuyin>))|
            (?:(<win>({LS})?(?P<WIN>.+?|[{NUM2}{LS}]+)</win>))
        """.format(**substitutions),
        re.VERBOSE,
    )

    re_buyin = re.compile(r"""(?:(<totalbuyin>(?P<TOTBUYIN>.*)</totalbuyin>))""", re.VERBOSE)
    re_total_buyin = re.compile(
        r"""(?:(<buyin>(?P<BIAMT>[{NUM2}{LS}]+)\s\+\s)?(?P<BIRAKE>[{NUM2}{LS}]+)\s\+\s(?P<BIRAKE2>[{NUM2}{LS}]+)</buyin>)""".format(
            **substitutions,
        ),
        re.VERBOSE,
    )
    re_hand_info = re.compile(
        r'code="(?P<HID>[0-9]+)".*?<general>(.*?<startdate>(?P<DATETIME>[\.a-zA-Z-/: 0-9]+)</startdate>)?',
        re.MULTILINE | re.DOTALL,
    )
    re_player_info = re.compile(
        r"<player( "
        r'(seat="(?P<SEAT>[0-9]+)"'
        r'|name="{PLYR}"'
        r'|chips="({LS})?(?P<CASH>[\d.,\s]+)({LS})?"'
        r'|dealer="(?P<BUTTONPOS>(0|1))"'
        r'|win="({LS})?(?P<WIN>[\d.,\s]+)({LS})?"'
        r'|bet="({LS})?(?P<BET>[^"]+)({LS})?"'
        r'|rakeamount="({LS})?(?P<RAKEAMOUNT>[\d.,\s]+)({LS})?"'
        r'|addon="\d*"'
        r'|rebuy="\d*"'
        r'|merge="\d*"'
        r'|reg_code="[\d-]*"'
        r"))+\s*/>".format(**substitutions),
        re.MULTILINE,
    )

    re_board = re.compile(
        r'<cards( (type="(?P<STREET>Flop|Turn|River)"|player=""))+>(?P<CARDS>.+?)</cards>',
        re.MULTILINE,
    )
    re_end_of_hand = re.compile(r'<round id="END_OF_GAME"', re.MULTILINE)
    re_hero = re.compile(r"<nickname>(?P<HERO>.+)</nickname>", re.MULTILINE)
    re_hero_cards = re.compile(
        r"<cards( "
        r'(type="(Pocket|Second\sStreet|Third\sStreet|Fourth\sStreet|'
        r'Fifth\sStreet|Sixth\sStreet|River)"'
        r'|player="{PLYR}"))+>(?P<CARDS>.+?)</cards>'.format(**substitutions),
        re.MULTILINE,
    )
    # Original re_Action pattern (replaced by cleaner version below)
    re_action = re.compile(
        r'<action(?=(?:[^>]*\bno="(?P<ACT>\d+)"))(?=(?:[^>]*\bplayer="(?P<PNAME>[^"]+)"))(?=(?:[^>]*\btype="(?P<ATYPE>\d+)"))(?=(?:[^>]*\bsum="[^"]*?(?P<BET>\d+(?:\.\d+)?)"))[^>]*>',
        re.MULTILINE,
    )
    re_sits_out = re.compile(
        r'<event sequence="[0-9]+" type="SIT_OUT" player="(?P<PSEAT>[0-9])"/>',
        re.MULTILINE,
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
    re_max_seats = re.compile(r"<tablesize>(?P<SEATS>[0-9]+)</tablesize>", re.MULTILINE)
    re_tablename_mtt = re.compile(r"<tablename>(?P<TABLET>.+?)</tablename>", re.MULTILINE)
    re_tour_no = re.compile(r"(?P<TOURNO>\d+)$", re.MULTILINE)
    re_non_decimal = re.compile(r"[^\d.,]+")
    re_partial = re.compile("<startdate>", re.MULTILINE)
    re_uncalled_bets = re.compile(r"<uncalled_bet_enabled>true<\/uncalled_bet_enabled>")
    re_client_version = re.compile(r"<client_version>(?P<VERSION>[.\d]+)</client_version>")
    re_fpp = re.compile(r"Pts\s")


    def _raise_community_cards_error(self, hand_id: str, street: str) -> None:
        """Raise an error when community cards cannot be found."""
        error_msg = "iPokerToFpdb.readCommunityCards: No community cards found for hand %s, street: %s"
        log.error(error_msg, hand_id, street)
        raise FpdbParseError

    def cleanIPokerMoney(self, money_str: str) -> str:
        """Clean iPoker money strings that may contain currency symbols and leading zeros.

        Args:
            money_str (str): Raw money string like "002€" or "023€"

        Returns:
            str: Cleaned money string that can be converted to Decimal
        """
        if not money_str:
            return money_str

        # Remove currency symbols and non-decimal characters
        cleaned = self.re_non_decimal.sub("", money_str)

        # Remove leading zeros but preserve decimal structure
        if cleaned and cleaned != "0":
            # Handle cases like "002" -> "2", "023" -> "23", but keep "0.02" as is
            if "." not in cleaned and "," not in cleaned:
                # Pure integer with leading zeros
                cleaned = str(int(cleaned))
            elif "," in cleaned and cleaned.count(",") == 1:
                # European decimal format: "0,23"
                parts = cleaned.split(",")
                if len(parts) == self.DECIMAL_PARTS_COUNT:
                    integer_part = str(int(parts[0])) if parts[0] else "0"
                    decimal_part = parts[1]
                    cleaned = f"{integer_part},{decimal_part}"

        # Finally use the standard clearMoneyString
        return self.clearMoneyString(cleaned)

    def detectSkin(self, path: str) -> str:
        """Detect the iPoker skin from the file path."""
        path_lower = path.lower()

        # Map of path indicators to skin names (must match Sites table)
        skin_mapping = {
            "redbet": "Redbet Poker",
            "pmu": "PMU Poker",
            "fdj": "FDJ Poker",
            "en ligne": "FDJ Poker",
            "betclic": "Betclic Poker",
            "netbet": "NetBet Poker",
            "poker770": "Poker770",
            "barriere": "Barrière Poker",
            "titan": "Titan Poker",
            "bet365": "Bet365 Poker",
            "william hill": "William Hill Poker",
            "williamhill": "William Hill Poker",
            "paddy power": "Paddy Power Poker",
            "paddypower": "Paddy Power Poker",
            "betfair": "Betfair Poker",
            "coral": "Coral Poker",
            "genting": "Genting Poker",
            "mansion": "Mansion Poker",
            "winner": "Winner Poker",
            "ladbrokes": "Ladbrokes Poker",
            "sky": "Sky Poker",
            "sisal": "Sisal Poker",
            "lottomatica": "Lottomatica Poker",
            "eurobet": "Eurobet Poker",
            "snai": "Snai Poker",
            "goldbet": "Goldbet Poker",
            "casino barcelona": "Casino Barcelona Poker",
            "sportium": "Sportium Poker",
            "marca": "Marca Apuestas Poker",
            "everest": "Everest Poker",
            "bet-at-home": "Bet-at-home Poker",
            "mybet": "Mybet Poker",
            "betsson": "Betsson Poker",
            "betsafe": "Betsafe Poker",
            "nordicbet": "NordicBet Poker",
            "unibet": "Unibet Poker",
            "maria": "Maria Casino Poker",
            "leovegas": "LeoVegas Poker",
            "mr green": "Mr Green Poker",
            "expekt": "Expekt Poker",
            "coolbet": "Coolbet Poker",
            "chilipoker": "Chilipoker",
            "dafa": "Dafa Poker",
            "dafabet": "Dafabet Poker",
            "fun88": "Fun88 Poker",
            "betfred": "Betfred Poker",
            "guts": "Guts Poker",
            "sportingbet": "Sportingbet Poker",
            "multipoker": "MultiPoker",
            "red star": "Red Star Poker",
            "redstar": "Red Star Poker",
        }

        # Check each mapping
        for indicator, skin_name in skin_mapping.items():
            if indicator in path_lower:
                log.info("Detected iPoker skin: %s from path: %s", skin_name, path)
                return skin_name

        # Default to generic iPoker if no specific skin detected
        log.info("No specific iPoker skin detected from path: %s, using default 'iPoker'", path)
        return "iPoker"

    def getFileCreationTime(self) -> datetime.datetime:
        """Get the creation time of the current hand history file.

        Returns:
            datetime: File creation time or current time if file doesn't exist
        """
        try:
            if hasattr(self, "in_path") and self.in_path and self.in_path != "-":
                file_path = Path(self.in_path)
                if file_path.exists():
                    # Get file creation time (or modified time as fallback)
                    try:
                        creation_time = file_path.stat().st_ctime
                    except (OSError, AttributeError):
                        # Fallback to modification time if creation time not available
                        creation_time = file_path.stat().st_mtime

                    return datetime.datetime.fromtimestamp(creation_time, tz=ZoneInfo("UTC"))

        except (OSError, AttributeError, ValueError) as e:
            log.warning("Could not get file creation time: %s", e)

        # Fallback to current time
        log.warning("Using current time as fallback for missing startdate")
        return datetime.datetime.now(tz=ZoneInfo("UTC"))

    def compilePlayerRegexs(self, hand: Any) -> None:
        """Compile player-specific regular expressions for the hand.

        Args:
            hand: The hand object containing player information
        """
        log.debug("Compiling player regexes for hand: %s", hand)

    def playerNameFromSeatNo(self, seat_no: int, hand: Any) -> str | None:
        """Returns the name of the player from the given seat number.

        This special function is required because Carbon Poker records actions by seat number, not by the player's name.

        Args:
            seat_no (int): The seat number of the player.
            hand (Hand): The hand instance containing the players information.

        Returns:
            str: The name of the player from the given seat number.
        """
        log.debug("Searching for player name from seat_no: %s in hand: %s", seat_no, hand)
        for p in hand.players:
            log.debug("Checking player: %s", p)
            if p[0] == int(seat_no):
                log.debug("Found player: %s for seat_no: %s", p[1], seat_no)
                return p[1]
        log.debug("No player found for seat_no: %s", seat_no)
        return None

    def readSupportedGames(self) -> list[list[str]]:
        """Return a list of supported games, where each game is a list of strings.

        The first element of each game list is either "ring" or "tour".
        The second element of each game list is either "stud" or "hold".
        The third element of each game list is either "nl", "pl", or "fl".
        """
        supported_games = [
            ["ring", "stud", "fl"],  # ring game with stud format and fixed limit
            ["ring", "hold", "nl"],  # ring game with hold format and no limit
            ["ring", "hold", "pl"],  # ring game with hold format and pot limit
            ["ring", "hold", "fl"],  # ring game with hold format and fixed limit
            ["tour", "hold", "nl"],  # tournament with hold format and no limit
            ["tour", "hold", "pl"],  # tournament with hold format and pot limit
            ["tour", "hold", "fl"],  # tournament with hold format and fixed limit
            ["tour", "stud", "fl"],  # tournament with stud format and fixed limit
        ]
        log.debug("Supported games: %s", supported_games)
        return supported_games

    def parseHeader(self, hand_text: str, whole_file: str) -> str | None:
        """Parses the header of a hand history and returns the game type.

        Args:
            hand_text (str): The text containing the header of the hand history.
            whole_file (str): The entire text of the hand history.

        Returns:
            str: The game type, if it can be determined from the header or the whole file.
                None otherwise.

        Raises:
            FpdbParseError: If the hand history is an iPoker hand lacking actions/starttime.
            FpdbHandPartial: If the hand history is an iPoker partial hand history without a start date.
        """
        log.debug("Starting parseHeader with hand_text: %s and whole_file length: %s", hand_text[:200], len(whole_file))

        # Attempt to determine the game type from the hand text
        gametype = self.determineGameType(hand_text)
        log.debug("Game type determined from hand_text: %s", gametype)

        if gametype is None:
            # Fallback to determining the game type from the whole file
            gametype = self.determineGameType(whole_file)
            log.debug("Game type determined from whole_file: %s", gametype)

        if gametype is None:
            # Handle iPoker hands lacking actions/starttime and funnel them to partial
            if self.re_partial.search(whole_file):
                tmp = hand_text[:200]  # Limit to the first 200 characters for logging
                log.error("No game type found. Partial hand_text: '%s'", tmp)
                raise FpdbParseError

            # Missing startdate is no longer considered a partial since we can use file creation time as fallback
            log.warning(
                "No game type determined, but this may be due to missing startdate. "
                "Will attempt to use file creation time fallback.",
            )
            raise FpdbParseError

        log.debug("Game type successfully parsed: %s", gametype)
        return gametype

    def _parse_game_info_regexes(self, hand_text: str) -> tuple:
        """Parse the main game info regexes."""
        m = self.re_game_info.search(hand_text)
        if not m:
            log.debug("re_game_info regex did not match.")
            return None, None, None
        log.debug("re_game_info regex matched.")

        m2 = self.re_max_seats.search(hand_text)
        if m2:
            log.debug("re_max_seats regex matched.")
        else:
            log.debug("re_max_seats regex did not match.")

        m3 = self.re_tablename_mtt.search(hand_text)
        if m3:
            log.debug("re_tablename_mtt regex matched.")
        else:
            log.debug("re_tablename_mtt regex did not match.")

        log.debug("Initial groupdict from re_game_info: %s", m.groupdict())
        log.debug("Groupdict from re_max_seats: %s", m2.groupdict() if m2 else {})
        log.debug("Groupdict from re_tablename_mtt: %s", m3.groupdict() if m3 else {})

        return m, m2, m3

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

        session_info = {}
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
            r"(\w+(?:\s+\w+)*)\s+"
            r"(NL|PL|L|SL|БЛ|LP|No\s+limit|Pot\s+limit|Limit)\s*"
            r"\$?([0-9.,]+)/\$?([0-9.,]+)"
        )
        gametype_pattern_no_blinds = (
            r"(\w+(?:\s+\w+)*)\s+"
            r"(NL|PL|L|SL|БЛ|LP|No\s+limit|Pot\s+limit|Limit)\s*$"
        )

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
            filename = getattr(self, "in_path", "")
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

    def _create_tournament_summary_with_all_players(self, hand: Any, tournament_data: dict) -> None:  # noqa: C901, PLR0912, PLR0915
        """Create a TourneySummary with all players parsed from XML."""
        try:
            from decimal import Decimal

            from Database import Database
            from TourneySummary import TourneySummary

            log.info("Creating TourneySummary with all players")

            # Get database connection
            db = Database(self.config)

            # Create TourneySummary
            summary = TourneySummary(
                db=db,
                config=self.config,
                siteName=self.sitename,
                summaryText=getattr(self, "whole_file", hand.handText),
                builtFrom="HHC",
                header="",
            )

            # Set basic tournament info
            summary.tourNo = tournament_data.get("tourno")
            summary.tourneyName = tournament_data.get("tournament_name", "Unknown")
            summary.buyin = int(tournament_data.get("buyin_amount", Decimal("0")) * 100)
            summary.fee = int(tournament_data.get("fee_amount", Decimal("0")) * 100)
            summary.buyinCurrency = tournament_data.get("currency_symbol", "EUR")
            summary.currency = summary.buyinCurrency

            # Parse tournament data from session/general (not game/players)
            xml_source = getattr(self, "whole_file", hand.handText)

            # Get hero data from session/general
            hero_name = re.search(r"<nickname>([^<]*)</nickname>", xml_source)
            hero_place = re.search(r"<place>([^<]*)</place>", xml_source)
            hero_win = re.search(r"<win>([^<]*)</win>", xml_source)

            if hero_name:
                hero_name = hero_name.group(1)

                # Get hero rank (None if not found or N/A)
                hero_rank = None
                if hero_place and hero_place.group(1) != "N/A":
                    try:
                        hero_rank = int(hero_place.group(1))
                    except (ValueError, TypeError):
                        hero_rank = None

                # Get hero winnings (0 if not found)
                hero_winnings = 0
                if hero_win and hero_win.group(1) != "N/A":
                    try:
                        # Convert "0€" to 0 cents, "1€" to 100 cents, etc.
                        win_str = hero_win.group(1).replace("€", "").replace(",", ".")
                        hero_winnings = int(float(win_str) * 100) if win_str else 0
                    except (ValueError, TypeError):
                        hero_winnings = 0

                log.info("Hero data: %s, rank=%s, winnings=%s cents", hero_name, hero_rank, hero_winnings)

                # Add hero to tournament
                summary.addPlayer(hero_rank, hero_name, hero_winnings, summary.currency, None, None, None)

                # Get all other players from game/players but only their names (no wins/ranks)
                other_players = set()
                player_name_pattern = r'<player[^>]*name="([^"]*)"[^>]*'
                all_player_names = re.findall(player_name_pattern, xml_source)

                for player_name in all_player_names:
                    if player_name != hero_name:
                        other_players.add(player_name)

                log.info("Other players found: %s", list(other_players))

                # Add other players with unknown rank and no winnings
                for player_name in other_players:
                    log.debug("Adding other player %s: rank=None, winnings=0", player_name)
                    summary.addPlayer(None, player_name, 0, summary.currency, None, None, None)

            else:
                log.error("No hero found in XML")

            # Detect Twister and set lottery fields
            if "Twister" in summary.tourneyName:
                summary.isLottery = True
                # Calculate multiplier from rewarddrawn vs buyin
                rewarddrawn_match = re.search(r"<rewarddrawn>([^<]*)</rewarddrawn>", xml_source)
                if rewarddrawn_match:
                    try:
                        rewarddrawn = Decimal(rewarddrawn_match.group(1).replace(",", ".").replace("€", ""))
                        if summary.buyin > 0:
                            multiplier = rewarddrawn / (summary.buyin / 100)
                            summary.tourneyMultiplier = int(multiplier) if multiplier > 1 else 1
                        else:
                            summary.tourneyMultiplier = 1
                    except (ValueError, TypeError, decimal.InvalidOperation):
                        summary.tourneyMultiplier = 1
                else:
                    summary.tourneyMultiplier = 1
            else:
                summary.isLottery = False
                summary.tourneyMultiplier = 1

            log.info("TourneySummary created: lottery=%s, multiplier=%s", summary.isLottery, summary.tourneyMultiplier)

            # Insert into database
            summary.insertOrUpdate()

            log.info("TourneySummary successfully inserted into database")

        except (ValueError, TypeError, AttributeError, ImportError):
            log.exception("Error creating TourneySummary")

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
            total = Decimal("0")
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

        tourney_info = {}
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
                self.tinfo["rewarddrawn"] = Decimal("0")
                self.tinfo["rewarddrawn_cents"] = 0
        else:
            self.tinfo["rewarddrawn"] = Decimal("0")
            self.tinfo["rewarddrawn_cents"] = 0

        # Calculate Twister multiplier (rewarddrawn / buyin)
        if self.tinfo["rewarddrawn"] > 0 and self.tinfo["buyin"] > 0:
            # Convert buyin from cents to euros for calculation
            buyin_euros = Decimal(self.tinfo["buyin"]) / 100
            self.tinfo["multiplier"] = self.tinfo["rewarddrawn"] / buyin_euros
            log.debug("Calculated Twister multiplier: %s (rewarddrawn: %s / buyin: %s)",
                     self.tinfo["multiplier"], self.tinfo["rewarddrawn"], buyin_euros)
        else:
            self.tinfo["multiplier"] = Decimal("0")
            log.debug("Cannot calculate multiplier: rewarddrawn=%s, buyin=%s",
                     self.tinfo["rewarddrawn"], self.tinfo["buyin"])

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
                self.tinfo["hero_winnings"] = Decimal("0")
                self.tinfo["hero_winnings_cents"] = 0
        else:
            self.tinfo["hero_winnings"] = Decimal("0")
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

    def _process_lh_game_type(self, mg: dict) -> dict:
        """Process LH game type."""
        if mg.get("GAME", "")[:2] == "LH":
            log.debug("Game starts with 'LH'. Setting CATEGORY to 'Holdem' and LIMIT to 'L'.")
            mg["CATEGORY"] = "Holdem"
            mg["LIMIT"] = "L"
            mg["BB"] = mg.get("LBB", mg.get("BB", ""))
            log.debug("Updated mg after 'LH' condition: %s", mg)
        return mg

    def _determine_base_category(self, mg: dict) -> bool:
        """Determine base and category for the game."""
        if "GAME" not in mg:
            return False

        if mg.get("CATEGORY") is None:
            log.debug("CATEGORY is None. Setting base='hold' and category='5_omahahi'.")
            self.info["base"], self.info["category"] = ("hold", "5_omahahi")
        else:
            category = mg["CATEGORY"]
            if category in self.games:
                self.info["base"], self.info["category"] = self.games[category]
                log.debug("Set base/category from games dict: %s, %s", self.info["base"], self.info["category"])
            else:
                log.error("Unknown CATEGORY '%s' encountered.", category)
                return False
        return True

    def _determine_limit_type(self, mg: dict) -> bool:
        """Determine limit type for the game."""
        if "LIMIT" not in mg:
            return True

        limit = mg["LIMIT"]
        if limit in self.limits:
            self.info["limitType"] = self.limits[limit]
            log.debug("Set limitType to '%s' from LIMIT '%s'.", self.info["limitType"], limit)
        else:
            log.error("Unknown LIMIT '%s' encountered.", limit)
            return False
        return True

    def _process_hero_info(self, mg: dict) -> None:
        """Process hero information."""
        if mg.get("HERO"):
            self.hero = mg["HERO"]
            log.debug("Set hero to '%s'.", self.hero)

    def _process_blinds_info(self, mg: dict) -> bool:
        """Process blinds information and determine if it's a tournament."""
        tourney = False

        if "SB" in mg:
            self.info["sb"] = self.clearMoneyString(mg["SB"])
            log.debug("Set sb to '%s'.", self.info["sb"])
            if not mg["SB"]:
                tourney = True
                log.debug("SB not set => marking as tournament.")

        if "BB" in mg:
            self.info["bb"] = self.clearMoneyString(mg["BB"])
            log.debug("Set bb to '%s'.", self.info["bb"])

        return tourney

    def _process_seats_info(self, mg2: dict) -> None:
        """Process seats information."""
        if "SEATS" in mg2:
            self.info["seats"] = mg2["SEATS"]
            log.debug("Set number of seats to '%s'.", self.info["seats"])

    def _process_uncalled_bets(self, hand_text: str) -> None:
        """Process uncalled bets settings."""
        if self.re_uncalled_bets.search(hand_text):
            self.uncalledbets = False
            log.debug("Uncalled bets disabled.")
        else:
            self.uncalledbets = True
            log.debug("Uncalled bets enabled.")
            mv = self.re_client_version.search(hand_text)
            if mv:
                major_version = mv.group("VERSION").split(".")[0]
                log.debug("Client version major number: %s", major_version)
                if int(major_version) >= self.MIN_CLIENT_VERSION_FOR_UNCALLED_BETS:
                    self.uncalledbets = False
                    log.debug("Client version >= 20 => Uncalled bets disabled.")

    def _process_tournament_info(self, mg: dict, mg3: dict, hand_text: str) -> bool:
        """Process tournament-specific information."""
        # Check if this is a tournament (type should already be set by _parse_xml_format)
        if self.info.get("type") != "tour":
            log.debug("Skipping tournament info processing - type is %s", self.info.get("type"))
            return False

        log.debug("Processing tournament-specific information.")

        if "TABLET" in mg3:
            self.info["table_name"] = mg3["TABLET"]
            log.debug("Table name: '%s'.", self.info["table_name"])

        self.tinfo = {}

        # Extract tourNo
        if not self._extract_tournament_number(mg):
            return False

        self.tablename = "1"
        self._set_buyin_currency(mg)
        self.tinfo["buyin"] = 0
        self.tinfo["fee"] = 0

        # Process tournament details based on client version
        if not self._process_tournament_details(mg, hand_text):
            return False

        # Fill tinfo from mg
        self._fill_tournament_info(mg)

        # Process buy-in information
        self._process_buyin_info(mg, hand_text)

        if self.tinfo["buyin"] == 0:
            self.tinfo["buyinCurrency"] = "FREE"
            log.debug("No buyin found, setting buyinCurrency=FREE")

        if self.tinfo.get("tourNo") is None:
            log.error("Could Not Parse tourNo")
            msg = "Could Not Parse tourNo"
            raise FpdbParseError(msg)

        return True

    def _extract_tournament_number(self, mg: dict) -> bool:
        """Extract tournament number from game info."""
        mt = self.re_tour_no.search(mg.get("TABLE", ""))
        if mt:
            self.tinfo["tourNo"] = mt.group("TOURNO")
            log.debug("Set tourNo from re_tour_no: %s", self.tinfo["tourNo"])
        else:
            # fallback if re_tour_no not matched
            tour_no = mg.get("TABLE", "").split(",")[-1].strip().split(" ")[0]
            if tour_no.isdigit():
                self.tinfo["tourNo"] = tour_no
                log.debug("Set tourNo from split TABLE: %s", tour_no)
            else:
                log.error("Failed to parse tourNo from TABLE.")
                return False
        return True

    def _set_buyin_currency(self, mg: dict) -> None:
        """Set buy-in currency."""
        if not mg.get("CURRENCY") or mg["CURRENCY"] == "fun":
            self.tinfo["buyinCurrency"] = "play"
            log.debug("Buy-in currency: play")
        else:
            self.tinfo["buyinCurrency"] = mg["CURRENCY"]
            log.debug("Buy-in currency: %s", self.tinfo["buyinCurrency"])

    def _process_tournament_details(self, mg: dict, hand_text: str) -> bool:
        """Process tournament details based on client version."""
        # Skip tournament processing for cash games
        if self.info.get("type") == "ring":
            log.debug("Skipping tournament details for cash game")
            return False

        client_match = self.re_client.search(hand_text)
        if client_match:
            re_client_split = ".".join(client_match["CLIENT"].split(".")[:2])
            log.debug("Client version split: '%s'", re_client_split)
        else:
            re_client_split = ""
            log.debug("No client version found.")

        # Parsing tournament info depending on client version
        if re_client_split == "23.5":  # betclic fr
            return self._process_betclic_tournament_info(mg, hand_text)
        return self._process_standard_tournament_info(mg, hand_text)

    def _process_betclic_tournament_info(self, mg: dict, hand_text: str) -> bool:
        """Process Betclic-specific tournament info."""
        # Skip tournament processing for cash games
        if self.info.get("type") == "ring":
            log.debug("Skipping Betclic tournament info for cash game")
            return False

        log.debug("Using re_game_info_trny (23.5)")
        matches = list(self.re_game_info_trny.finditer(hand_text))
        log.debug("Matches with re_game_info_trny: %s", len(matches))

        # Need at least 7 matches (index 0 to 6)
        if len(matches) > self.MIN_TOURNAMENT_MATCHES_REQUIRED:
            try:
                mg["TOURNO"] = matches[0].group("TOURNO")
                mg["NAME"] = matches[1].group("NAME")
                mg["REWARD"] = matches[2].group("REWARD")
                mg["PLACE"] = matches[3].group("PLACE")
                mg["BIAMT"] = matches[4].group("BIAMT")
                mg["BIRAKE"] = matches[4].group("BIRAKE")
                mg["BIRAKE2"] = matches[4].group("BIRAKE2")
                mg["TOTBUYIN"] = matches[5].group("TOTBUYIN")
                mg["WIN"] = matches[6].group("WIN")
                log.debug("Extracted tournament info: %s", mg)
            except IndexError:
                log.exception("Insufficient matches: %s found, need >6.", len(matches))
                log.debug(hand_text[:500])
                return False
            else:
                return True
        else:
            log.error("Not enough matches: %s found.", len(matches))
            log.debug(hand_text[:500])
            return False

    def _process_standard_tournament_info(self, mg: dict, hand_text: str) -> bool:
        """Process standard tournament info."""
        # Skip tournament processing for cash games
        if self.info.get("type") == "ring":
            log.debug("Skipping standard tournament info for cash game")
            return False

        log.debug("Using re_game_info_trny2")
        matches = list(self.re_game_info_trny2.finditer(hand_text))
        log.debug("Matches with re_game_info_trny2: %s", len(matches))

        for idx, mat in enumerate(matches):
            log.debug("Match %s: %s", idx, mat.groupdict())

        # Collect info in a dictionary
        tourney_info = {}
        for mat in matches:
            gd = mat.groupdict()
            for k, v in gd.items():
                if v and v.strip():
                    tourney_info[k] = v.strip()

        mg["TOURNO"] = tourney_info.get("TOURNO", mg.get("TOURNO"))
        mg["NAME"] = tourney_info.get("NAME", mg.get("NAME"))
        mg["PLACE"] = tourney_info.get("PLACE", mg.get("PLACE"))
        mg["BIAMT"] = tourney_info.get("BIAMT")
        mg["BIRAKE"] = tourney_info.get("BIRAKE")
        mg["TOTBUYIN"] = tourney_info.get("TOTBUYIN", mg.get("TOTBUYIN"))
        mg["WIN"] = tourney_info.get("WIN")

        # Handle case where only TOTBUYIN present
        if mg["BIAMT"] is None and mg["BIRAKE"] is None and mg["TOTBUYIN"]:
            total_buyin_str = self.cleanIPokerMoney(mg["TOTBUYIN"])
            if "Token" in hand_text:
                mg["BIAMT"] = total_buyin_str
                mg["BIRAKE"] = "0"
                log.debug("Token buy-in detected.")
            else:
                mg["BIAMT"] = total_buyin_str
                mg["BIRAKE"] = "0"
                log.debug("No BIAMT/BIRAKE found, fallback with TOTBUYIN only.")

        # Check essential info
        if not mg.get("TOURNO") or not mg.get("NAME") or not mg.get("PLACE") or not mg.get("TOTBUYIN"):
            log.error("Missing essential tournament info: %s", tourney_info)
            log.debug(hand_text[:500])
            return False

        log.debug("Consolidated tournament info: %s", mg)
        return True

    def _fill_tournament_info(self, mg: dict) -> None:
        """Fill tournament info from parsed data."""
        if mg.get("TOURNO"):
            self.tinfo["tour_name"] = mg.get("NAME", "")
            self.tinfo["tourNo"] = mg["TOURNO"]
            log.debug("Set tour_name=%s, tourNo=%s", self.tinfo["tour_name"], self.tinfo["tourNo"])

        if mg.get("PLACE") and mg["PLACE"] != "N/A":
            self.tinfo["rank"] = int(mg["PLACE"])
            log.debug("Set rank=%s", self.tinfo["rank"])

        if "winnings" not in self.tinfo:
            self.tinfo["winnings"] = 0
            log.debug("Initialized winnings=0")

        if mg.get("WIN") and mg["WIN"] != "N/A":
            try:
                winnings = int(100 * Decimal(self.cleanIPokerMoney(mg["WIN"])))
                self.tinfo["winnings"] += winnings
                log.debug("Added winnings: %s, total: %s", winnings, self.tinfo["winnings"])
            except Exception as e:
                log.exception("Error parsing WIN: %s", mg.get("WIN"))
                msg = "Error parsing winnings."
                raise FpdbParseError(msg) from e

    def _process_buyin_info(self, mg: dict, hand_text: str) -> None:
        """Process buy-in information."""
        if not mg.get("BIRAKE"):
            m_buyin = self.re_total_buyin.search(hand_text)
            if m_buyin:
                mg.update(m_buyin.groupdict())
                log.debug("Updated mg from re_total_buyin: %s", mg)
            elif mg.get("BIAMT"):
                mg["BIRAKE"] = "0"
                log.debug("Set BIRAKE=0 since no totalbuyin info but BIAMT found.")

        if mg.get("BIAMT") and self.re_fpp.match(mg["BIAMT"]):
            self.tinfo["buyinCurrency"] = "FPP"
            log.debug("FPP detected as buy-in currency.")

        if mg.get("BIRAKE"):
            self._process_birake_info(mg, hand_text)

    def _process_birake_info(self, mg: dict, hand_text: str) -> None:
        """Process BIRAKE information."""
        mg["BIRAKE"] = self.cleanIPokerMoney(mg["BIRAKE"])
        mg["BIAMT"] = self.cleanIPokerMoney(mg["BIAMT"])
        log.debug("Cleaned BIRAKE=%s, BIAMT=%s", mg["BIRAKE"], mg["BIAMT"])

        client_match = self.re_client.search(hand_text)
        re_client_split = ".".join(client_match["CLIENT"].split(".")[:2]) if client_match else ""

        if re_client_split == "23.5" and mg.get("BIRAKE2"):
            try:
                buyin2 = int(100 * Decimal(self.cleanIPokerMoney(mg["BIRAKE2"])))
                self.tinfo["buyin"] += buyin2
                log.debug("Added BIRAKE2 to buyin: %s. Total buyin: %s", buyin2, self.tinfo["buyin"])
            except Exception:
                log.exception("Error parsing BIRAKE2: %s", mg.get("BIRAKE2"))
                msg = "Error parsing BIRAKE2."
                raise FpdbParseError(msg) from None

            m4 = self.re_buyin.search(hand_text)
            if m4:
                try:
                    fee = int(100 * Decimal(self.cleanIPokerMoney(mg["BIRAKE"])))
                    self.tinfo["fee"] = fee
                    log.debug("Set fee=%s", fee)
                    buyin = int(100 * Decimal(self.cleanIPokerMoney(mg["BIRAKE2"])))
                    self.tinfo["buyin"] = buyin
                    log.debug("Set buyin=%s", buyin)
                except Exception:
                    log.exception("Error parsing fee or buyin from BIRAKE/BIRAKE2.")
                    msg = "Error parsing fee or buyin."
                    raise FpdbParseError(msg) from None

    def _process_ring_game_info(self, mg: dict, hand_text: str) -> bool:
        """Process ring game information."""
        log.debug("Processing ring game-specific information.")
        self.info["type"] = "ring"
        self.tablename = mg.get("TABLE", "")
        log.debug("Set tablename=%s", self.tablename)

        self._set_ring_currency(mg)
        return self._fix_limit_blinds(mg, hand_text)

    def _set_ring_currency(self, mg: dict) -> None:
        """Set currency for ring games."""
        if not mg.get("TABLECURRENCY") and not mg.get("CURRENCY"):
            self.info["currency"] = "play"
            log.debug("Currency=play")
        elif not mg.get("TABLECURRENCY"):
            self.info["currency"] = mg["CURRENCY"]
            log.debug("Currency set from CURRENCY=%s", self.info["currency"])
        else:
            self.info["currency"] = mg["TABLECURRENCY"]
            log.debug("Currency set from TABLECURRENCY=%s", self.info["currency"])

    def _fix_limit_blinds(self, mg: dict, hand_text: str) -> bool:
        """Fix limit blinds if needed."""
        if self.info.get("limitType") == "fl" and mg.get("BB") is not None:
            try:
                self.info["sb"] = self.Lim_Blinds[self.clearMoneyString(mg["BB"])][0]
                self.info["bb"] = self.Lim_Blinds[self.clearMoneyString(mg["BB"])][1]
                log.debug("Set sb=%s and bb=%s from Lim_Blinds", self.info["sb"], self.info["bb"])
            except KeyError:
                tmp = hand_text[:200]
                log.exception("No lookup in Lim_Blinds for '%s' - '%s'", mg.get("BB", ""), tmp)
                msg = "Lim_Blinds lookup failed."
                raise FpdbParseError(msg) from None
            else:
                return True
        return True

    def determineGameType(self, hand_text: str) -> dict | None:
        """Determine game type from hand text.

        Args:
            hand_text: The raw hand history text

        Returns:
            dict: Game type information including limit, base, category, etc.
        """
        log.debug("Starting determineGameType with hand_text: %s", hand_text[:200])

        # Detect skin from path and set sitename and site_id
        if hasattr(self, "in_path") and self.in_path:
            detected_skin = self.detectSkin(self.in_path)
            self.sitename = detected_skin
            if hasattr(self.config, "get_site_id"):
                site_id_result = self.config.get_site_id(self.sitename)
                if site_id_result:
                    self.site_id = site_id_result
                    log.debug("Set site_id to %s for skin %s", self.site_id, self.sitename)
                else:
                    log.warning("Could not find site ID for %s, using default iPoker ID", self.sitename)
                    self.sitename = "iPoker"
                    self.site_id = 14

        # First try to parse using the standard regex
        m, m2, m3 = self._parse_game_info_regexes(hand_text)

        # If that fails, try to parse XML format by combining session and game level info
        if not m and hasattr(self, "whole_file") and self.whole_file:
            log.debug("Standard regex failed, trying XML format parsing")
            return self._parse_xml_format(hand_text)

        if not m:
            return None

        # Initialize info and merge group dicts
        self.info = {}
        mg = m.groupdict()
        mg2 = m2.groupdict() if m2 else {}
        mg3 = m3.groupdict() if m3 else {}
        log.debug("Initial groupdict from re_game_info: %s", mg)
        log.debug("Groupdict from re_max_seats: %s", mg2)
        log.debug("Groupdict from re_tablename_mtt: %s", mg3)

        # Process LH game type
        self._process_lh_game_type(mg)

        # Determine base and category
        self._determine_base_category(mg)

        # Determine limit type
        self._determine_limit_type(mg)

        # Process hero information
        self._process_hero_info(mg)

        # Process blinds information
        self._process_blinds_info(mg)

        # Process seats information
        self._process_seats_info(mg2)

        # Process uncalled bets information
        self._process_uncalled_bets(hand_text)

        # Detect tournament vs ring game (check for tournament markers in whole file)
        if hasattr(self, "whole_file") and self.whole_file:
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

        # Process tournament information
        log.debug("Before tournament processing - type is: %s", self.info.get("type"))
        tourney = self._process_tournament_info(mg, mg3, hand_text)
        log.debug("Tournament processing result: %s", tourney)

        # Handle ring game specific logic
        if not tourney:
            log.debug("Tournament processing failed, handling as ring game")
            self._handle_ring_game_logic(mg, hand_text)

        log.debug("Final info: %s", self.info)
        return self.info

    def _handle_ring_game_logic(self, mg: dict, hand_text: str) -> None:
        """Handle ring game specific logic."""
        log.debug("Processing ring game-specific information.")
        self.info["type"] = "ring"
        self.tablename = mg.get("TABLE", "")
        log.debug("Set tablename=%s", self.tablename)

        if not mg.get("TABLECURRENCY") and not mg.get("CURRENCY"):
            self.info["currency"] = "play"
            log.debug("Currency=play")
        elif not mg.get("TABLECURRENCY"):
            self.info["currency"] = mg["CURRENCY"]
            log.debug("Currency set from CURRENCY=%s", self.info["currency"])
        else:
            self.info["currency"] = mg["TABLECURRENCY"]
            log.debug("Currency set from TABLECURRENCY=%s", self.info["currency"])

        # Fix limit blinds if needed
        if self.info.get("limitType") == "fl" and mg.get("BB") is not None:
            try:
                self.info["sb"] = self.Lim_Blinds[self.clearMoneyString(mg["BB"])][0]
                self.info["bb"] = self.Lim_Blinds[self.clearMoneyString(mg["BB"])][1]
                log.debug("Set sb=%s and bb=%s from Lim_Blinds", self.info["sb"], self.info["bb"])
            except KeyError:
                tmp = hand_text[:200]
                log.exception("No lookup in Lim_Blinds for '%s' - '%s'", mg.get("BB", ""), tmp)
                msg = "Lim_Blinds lookup failed."
                raise FpdbParseError(msg) from None

    def readSummaryInfo(self, _summary_info_list: Any) -> bool:
        """Read summary information from summary info list.

        Args:
            _summary_info_list: List of summary information

        Returns:
            bool: True if successful
        """
        log.info("enter method readSummaryInfo.")
        log.debug("Method readSummaryInfo non implemented.")
        return True

    def readSTP(self, _hand: Any) -> None:
        """Read STP (Sit and Go Tournament Pointer) information.

        Args:
            _hand: The hand object to process
        """
        log.debug("enter method readSTP.")
        log.debug("Method readSTP non implemented.")

    def readHandInfo(self, hand: Any) -> None:
        """Parses the hand text and extracts relevant information about the hand.

        Args:
            hand: An instance of the Hand class that represents the hand being parsed.

        Raises:
            FpdbParseError: If the hand text cannot be parsed.

        Returns:
            None
        """
        log.debug("Entering readHandInfo.")

        # Parse hand info from regex
        match = self._parse_hand_info_regex(hand.handText)

        # Set basic hand information
        self._set_basic_hand_info(hand, match)

        # Parse and set start time
        self._parse_start_time(hand, match)

        # Set tournament-specific information if applicable
        self._set_tournament_info(hand)

        log.debug("Exiting readHandInfo.")

    def _parse_hand_info_regex(self, hand_text: str) -> Any:
        """Parse hand info regex and return match object."""
        match = self.re_hand_info.search(hand_text)
        if match is None:
            tmp = hand_text[:200]
            log.error("iPokerToFpdb.readHandInfo: '%s'", tmp)
            raise FpdbParseError

        log.debug("HandInfo regex matched.")
        log.debug("Extracted groupdict: %s", match.groupdict())
        return match

    def _set_basic_hand_info(self, hand: Any, match: Any) -> None:
        """Set basic hand information from match object."""
        # Set the table name and maximum number of seats for the hand
        hand.tablename = self.tablename
        log.debug("Set hand.tablename: %s", hand.tablename)

        if self.info.get("seats"):
            hand.maxseats = int(self.info["seats"])
            log.debug("Set hand.maxseats: %s", hand.maxseats)

        # Set the hand ID for the hand
        hand.handid = match.group("HID")
        log.debug("Set hand.handid: %s", hand.handid)

    def _parse_start_time(self, hand: Any, match: Any) -> None:
        """Parse and set the start time for the hand."""
        datetime_str = match.group("DATETIME")
        if datetime_str is None:
            log.warning("No startdate found in hand %s. Using file creation time as fallback.", hand.handid)
            hand.startTime = self.getFileCreationTime()
            log.debug("Set hand.startTime from file creation time: %s", hand.startTime)
            return

        # Try different datetime parsing methods
        if self._try_parse_datetime_format1(hand, datetime_str):
            return

        if self._try_parse_default_format(hand, datetime_str):
            return

        self._try_parse_fallback_formats(hand, datetime_str)

    def _try_parse_datetime_format1(self, hand: Any, datetime_str: str) -> bool:
        """Try to parse datetime using format 1."""
        if m2 := self.re_date_time1.search(datetime_str):
            log.debug("Matched re_date_time1.")
            month = self.months[m2.group("M")]
            sec = m2.group("S") or "00"
            datetimestr = f"{m2.group('Y')}/{month}/{m2.group('D')} {m2.group('H')}:{m2.group('MIN')}:{sec}"
            hand.startTime = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S").replace(
                tzinfo=ZoneInfo("UTC"),
            )
            log.debug("Parsed hand.startTime: %s", hand.startTime)
            return True
        return False

    def _try_parse_default_format(self, hand: Any, datetime_str: str) -> bool:
        """Try to parse datetime using default format."""
        try:
            hand.startTime = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=ZoneInfo("UTC"),
            )
            log.debug("Parsed hand.startTime using default format: %s", hand.startTime)
        except ValueError:
            log.debug("Failed to parse datetime using default format.")
            return False
        else:
            return True

    def _try_parse_fallback_formats(self, hand: Any, datetime_str: str) -> None:
        """Try to parse datetime using fallback formats."""
        try:
            log.warning("Failed to parse datetime: %s. Trying re_date_time2 or re_date_time3.", datetime_str)
            if date_match := self.re_date_time2.search(datetime_str):
                log.debug("Matched re_date_time2.")
                datestr = "%d/%m/%Y %H:%M:%S" if "/" in datetime_str else "%d.%m.%Y %H:%M:%S"
                if date_match.group("S") is None:
                    datestr = "%d/%m/%Y %H:%M"
            else:
                date_match1 = self.re_date_time3.search(datetime_str)
                if date_match1 is None:
                    log.exception("iPokerToFpdb.readHandInfo Could not read datetime: '%s'", hand.handid)
                    raise FpdbParseError
                datestr = "%Y/%m/%d %H:%M:%S"
                if date_match1.group("S") is None:
                    datestr = "%Y/%m/%d %H:%M"

            hand.startTime = datetime.datetime.strptime(datetime_str, datestr).replace(
                tzinfo=ZoneInfo("UTC"),
            )
            log.debug("Parsed hand.startTime using fallback format: %s", hand.startTime)
        except ValueError as e:
            log.exception("iPokerToFpdb.readHandInfo Could not read datetime: '%s'", hand.handid)
            raise FpdbParseError from e

    def _set_tournament_info(self, hand: Any) -> None:
        """Set tournament-specific information if applicable."""
        if self.info["type"] == "tour":
            log.debug("Hand is a tournament hand, setting tournament-specific info.")
            hand.tourNo = self.tinfo["tourNo"]
            hand.buyinCurrency = self.tinfo["buyinCurrency"]
            hand.buyin = self.tinfo["buyin"]
            hand.fee = self.tinfo["fee"]
            hand.tablename = str(self.info["table_name"])
            log.debug(
                "Set tournament info: tourNo=%s, buyinCurrency=%s, buyin=%s, fee=%s, tablename=%s",
                hand.tourNo,
                hand.buyinCurrency,
                hand.buyin,
                hand.fee,
                hand.tablename,
            )

    def _initialize_player_data(self, hand: Any) -> tuple[dict, dict, dict]:
        """Initialize player data structures."""
        self.playerWinnings = {}
        plist = {}
        self.seat_mapping = {}  # Store seat mapping for tournaments
        hand.rake = Decimal("0.00")  # Initialize the total rake
        log.debug("Initialized playerWinnings, plist dictionaries, and hand.rake.")
        return self.playerWinnings, plist, self.seat_mapping

    def _extract_player_info(self, hand: Any) -> tuple[dict, list]:
        """Extract player information from hand text."""
        plist = {}
        original_seats = []

        m = self.re_player_info.finditer(hand.handText)
        log.debug("Running regex to find player information in hand text.")

        for a in m:
            log.info("🎯 SEAT DETECTION: Player %s detected at seat %s", a.group("PNAME"), a.group("SEAT"))
            log.debug("Matched player info: %s", a.groupdict())

            # Extract rake amount, defaulting to '0' if not present
            rake_amount = self.clearMoneyString(a.group("RAKEAMOUNT") or "0")
            hand.rake += Decimal(rake_amount)
            log.debug("Added rake amount %s for player %s. Total rake: %s", rake_amount, a.group("PNAME"), hand.rake)

            # Store original seat number
            original_seat = int(a.group("SEAT"))
            original_seats.append(original_seat)

            # Create a dictionary entry for the player
            win_amount = a.group("WIN")
            win_cleaned = self.clearMoneyString(win_amount) if win_amount else "0"

            plist[a.group("PNAME")] = [
                original_seat,
                self.clearMoneyString(a.group("CASH")),
                win_cleaned,
                False,
            ]
            log.info(
                "🎯 PLAYER ADDED: %s at seat %s, stack %s, winnings %s.",
                a.group("PNAME"),
                a.group("SEAT"),
                plist[a.group("PNAME")][1],
                plist[a.group("PNAME")][2],
            )

            # If the player is the button, set the button position
            if a.group("BUTTONPOS") == "1":
                hand.buttonpos = original_seat
                log.debug("Set button position to seat %s for player %s.", hand.buttonpos, a.group("PNAME"))

        return plist, original_seats

    def _validate_player_count(self, plist: dict, hand: Any) -> None:
        """Validate that there are enough players in the hand."""
        if len(plist) <= 1:
            log.warning(
                "iPokerToFpdb.readPlayerStacks: Less than 2 players in hand '%s'. Marking as partial.",
                hand.handid,
            )
            msg = f"iPoker partial hand history: Less than 2 players ({len(plist)} players found)"
            raise FpdbHandPartial(msg)

        log.debug("Player list extracted successfully. Total players: %s", len(plist))

    def _remap_tournament_seats(self, plist: dict, original_seats: list, hand: Any) -> None:
        """Remap seats for tournaments to sequential numbers."""
        if self.info["type"] != "tour":
            return

        # Sort original seats to maintain consistent mapping
        original_seats_sorted = sorted(original_seats)
        for i, original_seat in enumerate(original_seats_sorted):
            self.seat_mapping[original_seat] = i + 1

        log.info("🎯 SEAT MAPPING: %s", self.seat_mapping)

        # Remap button position if needed
        if hand.buttonpos and hand.buttonpos in self.seat_mapping:
            old_button = hand.buttonpos
            hand.buttonpos = self.seat_mapping[hand.buttonpos]
            log.info("🎯 BUTTON REMAPPED: %s -> %s", old_button, hand.buttonpos)

        # Remap seats in plist
        for pname in plist:
            old_seat = plist[pname][0]
            new_seat = self.seat_mapping.get(old_seat, old_seat)
            plist[pname][0] = new_seat
            log.info("🎯 SEAT REMAPPED: %s %s -> %s", pname, old_seat, new_seat)

    def _add_players_to_hand(self, plist: dict, hand: Any) -> None:
        """Add players to the hand object."""
        for pname in plist:
            seat, stack, win, sitout = plist[pname]
            log.info("🎯 ADDING TO HAND: %s at seat %s, stack %s, winnings %s", pname, seat, stack, win)
            hand.addPlayer(seat, pname, stack, None, sitout)
            if Decimal(win) != 0:
                self.playerWinnings[pname] = win
                log.debug("Player %s has winnings: %s", pname, win)

    def _determine_max_seats(self, hand: Any) -> None:
        """Determine the maximum number of seats."""
        # Log final hand.players structure
        log.info("🎯 FINAL HAND.PLAYERS: %s", [f"seat{p[0]}:{p[1]}" for p in hand.players])
        log.info("🎯 MAXSEATS WILL BE: %s", hand.maxseats if hand.maxseats else "TO_BE_DETERMINED")

        # Set the maxseats attribute in the Hand object if it is not already set
        if hand.maxseats is None:
            log.info("🎯 DETERMINING MAXSEATS...")
            if self.info["type"] == "tour" and self.maxseats == 0:
                hand.maxseats = self.guessMaxSeats(hand)
                self.maxseats = hand.maxseats
                log.info("🎯 GUESSED MAXSEATS for tournament: %s", hand.maxseats)
            elif self.info["type"] == "tour":
                hand.maxseats = self.maxseats
                log.info("🎯 SET MAXSEATS from tournament info: %s", hand.maxseats)
            else:
                hand.maxseats = None
                log.info("🎯 MAXSEATS could not be determined and remains None")
        else:
            log.info("🎯 MAXSEATS already set: %s", hand.maxseats)

        log.info("🎯 FINAL MAXSEATS: %s", hand.maxseats)

    def readPlayerStacks(self, hand: Any) -> None:
        """Parse and read player stacks and positions from hand text.

        Args:
            hand: The hand object to populate with player information
        """
        log.debug("Entering readPlayerStacks for hand: %s", hand.handid)

        # Initialize data structures
        self._initialize_player_data(hand)

        # Extract player information
        plist, original_seats = self._extract_player_info(hand)

        # Validate player count
        self._validate_player_count(plist, hand)

        # Remap seats for tournaments
        self._remap_tournament_seats(plist, original_seats, hand)

        # Add players to hand
        self._add_players_to_hand(plist, hand)

        # Determine max seats
        self._determine_max_seats(hand)

        log.debug("Exiting readPlayerStacks.")

    def markStreets(self, hand: Any) -> None:
        """Extracts the rounds of a hand and adds them to the Hand object.

        Args:
            hand (Hand): the Hand object to which the rounds will be added
        """
        log.debug("Entering markStreets for hand: %s", hand.handid)

        if hand.gametype["base"] in ("hold"):
            log.debug("Parsing streets for Hold'em game.")
            m = re.search(
                r'(?P<PREFLOP>.+(?=<round no="2">)|.+)'  # Preflop round
                r'(<round no="2">(?P<FLOP>.+(?=<round no="3">)|.+))?'  # Flop round
                r'(<round no="3">(?P<TURN>.+(?=<round no="4">)|.+))?'  # Turn round
                r'(<round no="4">(?P<RIVER>.+))?',  # River round
                hand.handText,
                re.DOTALL,
            )
        elif hand.gametype["base"] in ("stud"):
            log.debug("Parsing streets for Stud game.")
            if hand.gametype["category"] == "5_studhi":
                log.debug("Parsing streets for 5-card Stud High game.")
                m = re.search(
                    r'(?P<ANTES>.+(?=<round no="2">)|.+)'  # Antes round
                    r'(<round no="2">(?P<SECOND>.+(?=<round no="3">)|.+))?'  # Second round
                    r'(<round no="3">(?P<THIRD>.+(?=<round no="4">)|.+))?'  # Third round
                    r'(<round no="4">(?P<FOURTH>.+(?=<round no="5">)|.+))?'  # Fourth round
                    r'(<round no="5">(?P<FIFTH>.+))?',  # Fifth round
                    hand.handText,
                    re.DOTALL,
                )
            else:
                log.debug("Parsing streets for 7-card Stud High/Low game.")
                m = re.search(
                    r'(?P<ANTES>.+(?=<round no="2">)|.+)'  # Antes round
                    r'(<round no="2">(?P<THIRD>.+(?=<round no="3">)|.+))?'  # Third round
                    r'(<round no="3">(?P<FOURTH>.+(?=<round no="4">)|.+))?'  # Fourth round
                    r'(<round no="4">(?P<FIFTH>.+(?=<round no="5">)|.+))?'  # Fifth round
                    r'(<round no="5">(?P<SIXTH>.+(?=<round no="6">)|.+))?'  # Sixth round
                    r'(<round no="6">(?P<SEVENTH>.+))?',  # Seventh round
                    hand.handText,
                    re.DOTALL,
                )

        if m:
            log.debug("Streets regex matched. Groups: %s", m.groupdict())
            hand.addStreets(m)
            log.debug("Streets added to hand object.")
        else:
            log.warning("No streets matched for hand: %s", hand.handid)

        log.debug("Exiting markStreets.")

    def readCommunityCards(self, hand: Any, street: str) -> None:
        """Parse the community cards for the given street and set them in the hand object.

        Args:
            hand (Hand): The hand object.
            street (str): The street to parse the community cards for.

        Raises:
            FpdbParseError: If the community cards could not be parsed.

        Returns:
            None
        """
        log.debug("Entering readCommunityCards for hand: %s, street: %s", hand.handid, street)
        cards = []

        try:
            # Search for the board cards in the hand's streets
            if m := self.re_board.search(hand.streets[street]):
                log.debug("Regex matched for community cards on street: %s. Match groups: %s", street, m.groupdict())
                # Split the card string into a list of cards
                cards = m.group("CARDS").strip().split(" ")
                log.debug("Extracted raw cards: %s", cards)

                # Format the cards
                cards = [c[1:].replace("10", "T") + c[0].lower() for c in cards]
                log.debug("Formatted cards: %s", cards)

                # Set the community cards in the hand object
                hand.setCommunityCards(street, cards)
                log.debug("Community cards set for street %s: %s", street, cards)
            else:
                # Log an error if the board cards could not be found
                self._raise_community_cards_error(hand.handid, street)
        except Exception:
            log.exception(
                "Exception occurred while reading community cards for hand %s, street: %s",
                hand.handid,
                street,
            )
            raise

        log.debug("Exiting readCommunityCards for hand: %s, street: %s", hand.handid, street)

    def readAntes(self, hand: Any) -> None:
        """Reads the antes for each player in the given hand.

        Args:
            hand (Hand): The hand to read the antes from.

        Returns:
            None
        """
        log.debug("Entering readAntes for hand: %s", hand.handid)

        # Debug: show players in hand
        player_names = [player[1] for player in hand.players]
        log.debug("Players in hand: %s", player_names)

        # Find all the antes in the hand text using a regular expression
        m = self.re_action.finditer(hand.handText)
        log.debug("Searching for antes in hand text.")

        # Loop through each ante found
        for a in m:
            log.debug("Matched action: %s", a.groupdict())
            # If the ante is of type 15, add it to the hand
            if a.group("ATYPE") == "15":
                player_name = a.group("PNAME")
                ante_amount = self.clearMoneyString(a.group("BET"))
                log.debug("Adding ante for player: %s, amount: %s", player_name, ante_amount)

                # Check if player exists before adding ante
                if player_name not in player_names:
                    log.warning("Player %s not found in hand players list: %s. Skipping ante.",
                               player_name, player_names)
                    continue

                hand.addAnte(player_name, ante_amount)

        log.debug("Exiting readAntes for hand: %s", hand.handid)

    def readBringIn(self, hand: Any) -> None:
        """Read the bring-in for a hand and set sb/bb values if not already set.

        Args:
            hand (Hand): The hand object for which to read the bring-in.

        Returns:
            None
        """
        log.debug("Entering readBringIn for hand: %s", hand.handid)
        if hand.gametype["sb"] is None and hand.gametype["bb"] is None:
            hand.gametype["sb"] = "1"  # default small blind value
            hand.gametype["bb"] = "2"  # default big blind value
            log.debug("Small blind and big blind not set. Default values assigned: sb=1, bb=2.")
        log.debug("Exiting readBringIn for hand: %s", hand.handid)

    def readBlinds(self, hand: Any) -> None:
        """Parses hand history to extract blind information for each player in the hand.

        :param hand: Hand object containing the hand history.
        :type hand: Hand
        """
        log.debug("Entering readBlinds for hand: %s", hand.handid)

        # Debug: show players in hand
        player_names = [player[1] for player in hand.players]
        log.debug("Players in hand: %s", player_names)

        # Find all actions in the preflop street
        log.debug("Searching for small blind actions in PREFLOP street.")
        for a in self.re_action.finditer(hand.streets["PREFLOP"]):
            if a.group("ATYPE") == "1":
                player_name = a.group("PNAME")
                sb_amount = self.clearMoneyString(a.group("BET"))
                log.debug("Small blind detected: Player=%s, Amount=%s", player_name, sb_amount)

                # Check if player exists before adding blind
                if player_name not in player_names:
                    log.warning("Player %s not found in hand players list: %s. Skipping small blind.",
                               player_name, player_names)
                    continue

                hand.addBlind(player_name, "small blind", sb_amount)
                if not hand.gametype["sb"]:
                    hand.gametype["sb"] = sb_amount
                    log.debug("Small blind amount set in gametype: %s", sb_amount)

        # Find all actions in the preflop street for big blinds
        log.debug("Searching for big blind actions in PREFLOP street.")
        m = self.re_action.finditer(hand.streets["PREFLOP"])
        blinds = {
            int(a.group("ACT")): a.groupdict()
            for a in m
            if a.group("ATYPE") == "2" and a.group("PNAME") in player_names
        }
        log.debug("Big blinds found: %s players.", len(blinds))

        for b in sorted(blinds.keys()):
            blind = blinds[b]
            player_name = blind["PNAME"]
            bet_amount = self.clearMoneyString(blind["BET"])
            blind_type = "big blind"
            log.debug("Processing big blind: Player=%s, Amount=%s", player_name, bet_amount)

            if not hand.gametype["bb"]:
                hand.gametype["bb"] = bet_amount
                log.debug("Big blind amount set in gametype: %s", bet_amount)
            elif hand.gametype["sb"]:
                bb = Decimal(hand.gametype["bb"])
                amount = Decimal(bet_amount)
                if amount > bb:
                    blind_type = "both"
                    log.debug("Player %s posted both blinds: Amount=%s", player_name, bet_amount)
            hand.addBlind(player_name, blind_type, bet_amount)

        # Fix tournament blinds if necessary
        log.debug("Fixing tournament blinds if necessary.")
        self.fixTourBlinds(hand)

        log.debug("Exiting readBlinds for hand: %s", hand.handid)

    def fixTourBlinds(self, hand: Any) -> None:
        """Fix tournament blinds if small blind is missing or sb/bb is all-in.

        :param hand: A dictionary containing the game type information.
        :return: None
        """
        log.debug("Entering fixTourBlinds for hand: %s", hand.handid)
        if hand.gametype["type"] != "tour":
            log.debug("Hand type is not 'tour'. Exiting fixTourBlinds.")
            return

        log.debug("Initial gametype blinds: sb=%s, bb=%s", hand.gametype["sb"], hand.gametype["bb"])
        if hand.gametype["sb"] is None and hand.gametype["bb"] is None:
            hand.gametype["sb"] = "1"
            hand.gametype["bb"] = "2"
            log.debug("Blinds missing. Default values assigned: sb=1, bb=2.")
        elif hand.gametype["sb"] is None:
            hand.gametype["sb"] = str(int(int(hand.gametype["bb"]) // 2))
            log.debug("Small blind missing. Calculated and set to: sb=%s", hand.gametype["sb"])
        elif hand.gametype["bb"] is None:
            hand.gametype["bb"] = str(int(hand.gametype["sb"]) * 2)
            log.debug("Big blind missing. Calculated and set to: bb=%s", hand.gametype["bb"])

        if int(hand.gametype["bb"]) // 2 != int(hand.gametype["sb"]):
            if int(hand.gametype["bb"]) // 2 < int(hand.gametype["sb"]):
                hand.gametype["bb"] = str(int(hand.gametype["sb"]) * 2)
                log.debug("Big blind adjusted to match small blind: bb=%s", hand.gametype["bb"])
            else:
                hand.gametype["sb"] = str(int(hand.gametype["bb"]) // 2)
                log.debug("Small blind adjusted to match big blind: sb=%s", hand.gametype["sb"])
        log.debug("Final gametype blinds: sb=%s, bb=%s", hand.gametype["sb"], hand.gametype["bb"])
        log.debug("Exiting fixTourBlinds for hand: %s", hand.handid)

    def readButton(self, hand: Any) -> None:
        """Placeholder for future implementation of button reading."""
        log.debug("Entering readButton for hand: %s. Currently no implementation.", hand.handid)

    def readHoleCards(self, hand: Any) -> None:
        """Parse a Hand object to extract hole card information for each player on each street.

        Adds the hole card information to the Hand object.

        Args:
            hand: Hand object to extract hole card information from

        Returns:
            None
        """
        log.debug("Entering readHoleCards for hand: %s", hand.handid)

        # Process initial streets (PREFLOP, DEAL)
        self._process_initial_streets(hand)

        # Process remaining streets
        self._process_remaining_streets(hand)

        log.debug("Exiting readHoleCards for hand: %s", hand.handid)

    def _process_initial_streets(self, hand: Any) -> None:
        """Process initial streets (PREFLOP, DEAL) for hero's cards."""
        for street in ("PREFLOP", "DEAL"):
            if street in hand.streets:
                log.debug("Processing street: %s for hero's cards.", street)
                for found in self.re_hero_cards.finditer(hand.streets[street]):
                    player = found.group("PNAME")
                    cards = self._normalize_cards(found.group("CARDS").split(" "))

                    if hasattr(self, 'hero') and player == self.hero and cards[0]:
                        hand.hero = player
                        log.debug("Hero identified: %s with cards: %s", player, cards)

                    # Check if player exists in hand before adding hole cards
                    player_names = [p[1] for p in hand.players]  # Extract player names from hand.players
                    if player not in player_names:
                        log.warning("Skipping hole cards for unknown player '%s' in hand '%s'", player, hand.handid)
                        continue

                    hand.addHoleCards(
                        street,
                        player,
                        closed=cards,
                        shown=True,
                        mucked=False,
                        dealt=True,
                    )

    def _process_remaining_streets(self, hand: Any) -> None:
        """Process remaining streets for all players."""
        for street, text in hand.streets.items():
            if not text or street in ("PREFLOP", "DEAL"):
                continue  # already done these
            log.debug("Processing street: %s for all players.", street)
            for found in self.re_hero_cards.finditer(text):
                player = found.group("PNAME")
                if player is not None:
                    self._process_player_hole_cards(hand, street, player, found)

    def _process_player_hole_cards(self, hand: Any, street: str, player: str, found: Any) -> None:
        """Process hole cards for a specific player on a specific street."""
        # Check if player exists in hand before processing hole cards
        player_names = [p[1] for p in hand.players]  # Extract player names from hand.players
        if player not in player_names:
            log.warning(
                "Skipping hole cards for unknown player '%s' in hand '%s' on street '%s'",
                player,
                hand.handid,
                street,
            )
            return

        cards = found.group("CARDS").split(" ")
        newcards, oldcards = self._categorize_cards(cards, street, player)

        if street == "THIRD" and len(newcards) == self.THIRD_STREET_CARDS_COUNT and hasattr(self, 'hero') and self.hero == player:
            self._process_third_street_hero(hand, street, player, newcards)
        elif street == "SECOND" and len(newcards) == self.SECOND_STREET_CARDS_COUNT and hasattr(self, 'hero') and self.hero == player:
            self._process_second_street_hero(hand, street, player, newcards)
        else:
            self._process_standard_hole_cards(hand, street, player, newcards, oldcards)

    def _normalize_cards(self, cards: list[str]) -> list[str]:
        """Normalize card format."""
        return [c[1:].replace("10", "T") + c[0].lower().replace("x", "") for c in cards]

    def _categorize_cards(self, cards: list[str], street: str, player: str) -> tuple[list[str], list[str]]:
        """Categorize cards into new and old cards based on street and player."""
        if street == "SEVENTH" and hasattr(self, 'hero') and self.hero != player:
            newcards = []
            oldcards = [c[1:].replace("10", "T") + c[0].lower() for c in cards if c[0].lower() != "x"]
        else:
            newcards = [c[1:].replace("10", "T") + c[0].lower() for c in cards if c[0].lower() != "x"]
            oldcards = []
        return newcards, oldcards

    def _process_third_street_hero(self, hand: Any, street: str, player: str, newcards: list[str]) -> None:
        """Process hero cards on THIRD street."""
        hand.hero = player
        hand.dealt.add(player)
        hand.addHoleCards(
            street,
            player,
            closed=newcards[:2],
            open=[newcards[2]],
            shown=True,
            mucked=False,
            dealt=False,
        )
        log.debug("Hero cards on THIRD street: %s (closed), %s (open)", newcards[:2], newcards[2])

    def _process_second_street_hero(self, hand: Any, street: str, player: str, newcards: list[str]) -> None:
        """Process hero cards on SECOND street."""
        hand.hero = player
        hand.dealt.add(player)
        hand.addHoleCards(
            street,
            player,
            closed=[newcards[0]],
            open=[newcards[1]],
            shown=True,
            mucked=False,
            dealt=False,
        )
        log.debug("Hero cards on SECOND street: %s (closed), %s (open)", newcards[0], newcards[1])

    def _process_standard_hole_cards(
        self,
        hand: Any,
        street: str,
        player: str,
        newcards: list[str],
        oldcards: list[str],
    ) -> None:
        """Process standard hole cards."""
        hand.addHoleCards(
            street,
            player,
            open=newcards,
            closed=oldcards,
            shown=True,
            mucked=False,
            dealt=False,
        )
        log.debug("Player %s cards on %s: %s (open), %s (closed)", player, street, newcards, oldcards)

    def _process_action(self, hand: Any, street: str, action: dict) -> None:
        """Process a single action and add it to the hand."""
        atype = action["ATYPE"]
        player = action["PNAME"]
        bet = self.clearMoneyString(action["BET"])

        log.debug("Processing action: Player=%s, Type=%s, Bet=%s", player, atype, bet)

        action_handlers = {
            "0": lambda: hand.addFold(street, player),
            "4": lambda: hand.addCheck(street, player),
            "3": lambda: hand.addCall(street, player, bet),
            "23": lambda: hand.addRaiseTo(street, player, bet),
            "6": lambda: hand.addRaiseBy(street, player, bet),
            "5": lambda: hand.addBet(street, player, bet),
            "16": lambda: hand.addBringIn(player, bet),
            "7": lambda: hand.addAllIn(street, player, bet),
            "9": lambda: hand.addFold(street, player),
        }

        if atype in action_handlers:
            action_handlers[atype]()
            self._log_action_added(atype, player, street, bet)
        elif atype == "15":
            log.debug("Ante action skipped for player %s (handled in readAntes).", player)
        elif atype in ["1", "2", "8"]:
            log.debug("Blind or no-action skipped for player %s (Type=%s).", player, atype)
        else:
            log.error("Unimplemented readAction: Player=%s, Type=%s", player, atype)

    def _log_action_added(self, atype: str, player: str, street: str, bet: str) -> None:
        """Log the action that was added."""
        action_messages = {
            "0": f"Added fold for player {player} on street {street}.",
            "4": f"Added check for player {player} on street {street}.",
            "3": f"Added call for player {player} on street {street}, Bet={bet}.",
            "23": f"Added raise to {bet} for player {player} on street {street}.",
            "6": f"Added raise by {bet} for player {player} on street {street}.",
            "5": f"Added bet of {bet} for player {player} on street {street}.",
            "16": f"Added bring-in of {bet} for player {player}.",
            "7": f"Added all-in of {bet} for player {player} on street {street}.",
            "9": f"Player {player} sitting out, added fold for street {street}.",
        }

        if atype in action_messages:
            log.debug(action_messages[atype])

    def readAction(self, hand: Any, street: str) -> None:  # noqa: C901, PLR0912
        """Extracts actions from a hand and adds them to the corresponding street in a Hand object.

        Args:
            hand (Hand): Hand object to which the actions will be added.
            street (str): Name of the street in the hand (PREFLOP, FLOP, etc.).

        Returns:
            None
        """
        log.debug("Entering readAction for hand: %s, street: %s", hand.handid, street)

        # Debug: show players in hand
        player_names = [player[1] for player in hand.players]
        log.debug("Players in hand: %s", player_names)

        # HH format doesn't actually print the actions in order!
        m = self.re_action.finditer(hand.streets[street])
        actions = {}
        for a in m:
            actions[int(a.group("ACT"))] = a.groupdict()

        for a in sorted(actions.keys()):
            action = actions[a]
            atype = action["ATYPE"]
            player = action["PNAME"]
            bet = self.clearMoneyString(action["BET"])
            log.debug("Processing action: street=%s, player=%s, atype=%s, bet=%s", street, player, atype, bet)

            # Check if player exists in hand before processing actions
            if player not in player_names:
                log.warning("Player %s not found in hand players list: %s. Skipping action type %s.",
                           player, player_names, atype)
                continue

            if atype == "0":
                hand.addFold(street, player)
            elif atype == "4":
                hand.addCheck(street, player)
            elif atype == "3":
                hand.addCall(street, player, bet)
            elif atype == "23":  # Raise to
                hand.addRaiseTo(street, player, bet)
            elif atype == "6":  # Raise by
                hand.addRaiseBy(street, player, bet)
            elif atype == "5":
                hand.addBet(street, player, bet)
            elif atype == "16":  # BringIn
                hand.addBringIn(player, bet)
            elif atype == "7":
                hand.addAllIn(street, player, bet)
            elif atype == "15":  # Ante
                pass  # Antes dealt with in readAntes
            elif atype in ("1", "2", "8"):  # sb/bb/no action this hand (joined table)
                pass
            elif atype == "9":  # Sitting out
                hand.addFold(street, player)
            else:
                log.error("Unimplemented readAction: player='%s' atype='%s'", player, atype)

        log.debug("Exiting readAction for hand: %s, street: %s", hand.handid, street)

    def readShowdownActions(self, hand: Any) -> None:
        """Reads showdown actions and updates the hand object.

        Args:
            hand (Hand): The hand object to update with showdown actions.

        Returns:
            None
        """
        log.debug("Entering readShowdownActions for hand: %s", hand.handid)
        # Placeholder for showdown action logic
        log.debug("Currently no implementation for readShowdownActions.")
        log.debug("Exiting readShowdownActions for hand: %s", hand.handid)

    def readCollectPot(self, hand: Any) -> None:
        """Read and process pot collection information.

        Args:
            hand: The hand object to update with pot information
        """
        log.info("Entering readCollectPot method")

        # Activer les mises non égalisées
        hand.setUncalledBets(True)

        # Initialiser le pot total à zéro
        total_pot = Decimal("0.00")

        # Parcourir les informations des joueurs pour identifier les pots collectés
        for m in self.re_player_info.finditer(hand.handText):
            player = m.group("PNAME")
            pot = m.group("WIN")
            if pot:  # Vérifier si un montant de gain est présent
                pot_value = self.clearMoneyString(pot)
                total_pot += Decimal(pot_value)  # Ajouter le montant au pot total
                hand.addCollectPot(player=player, pot=pot_value)
                log.debug("Player collected pot method: readCollectPot, player: %s, amount: %s", player, pot_value)
            else:
                log.debug("No winnings recorded for player: %s", player)

        # Ajouter le rake au pot total
        total_pot += hand.rake or Decimal("0.00")

        # Mettre à jour le total pot dans l'objet hand
        hand.totalpot = total_pot
        log.debug("Total pot calculated: %s, Total rake: %s", hand.totalpot, hand.rake)

        log.info("Exiting readCollectPot method")

    def readShownCards(self, hand: Any) -> None:
        """Reads shown cards and updates the hand object.

        Args:
            hand (Hand): The hand object to update with shown cards.

        Returns:
            None
        """
        log.debug("Entering readShownCards for hand: %s", hand.handid)
        # Placeholder for shown cards logic
        log.debug("Currently no implementation for readShownCards.")
        log.debug("Exiting readShownCards for hand: %s", hand.handid)

    def readTourneyResults(self, hand: Any) -> None:
        """Read and process tournament results and rankings.

        Args:
            hand: The hand object containing tournament information
        """
        log.info("Entering readTourneyResults method")

        # Skip tournament processing for cash games
        if hand.gametype and hand.gametype.get("type") == "ring":
            log.debug("Skipping tournament results for cash game")
            log.info("Exiting readTourneyResults method")
            return

        # Initialize data structures
        self._initialize_tournament_data(hand)

        # Parse tournament information
        tournament_data = self._parse_tournament_data(hand.handText)

        # Set tournament attributes
        self._set_tournament_attributes(tournament_data, hand)

        # Process players and winnings
        self._process_tournament_players(hand, tournament_data)

        # Create TourneySummary with all players (only once per tournament)
        if not hasattr(self, "tournament_summary_created"):
            self._create_tournament_summary_with_all_players(hand, tournament_data)
            self.tournament_summary_created = True

        log.info("Exiting readTourneyResults method")

    def _initialize_tournament_data(self, hand: Any) -> None:
        """Initialize tournament data structures."""
        hand.winnings = {}
        hand.ranks = {}
        hand.playersIn = []
        hand.isProgressive = False
        log.debug("Initialized tournament data structures method: iPoker:readTourneyResults, is_progressive: False")

    def _parse_tournament_data(self, hand_text: str) -> dict:  # noqa: C901, PLR0912, PLR0915
        """Parse tournament data from hand text."""
        tournament_data = {
            "buyin_amount": Decimal("0"),
            "fee_amount": Decimal("0"),
            "totbuyin_amount": Decimal("0"),
            "currency_symbol": "EUR",
            "tourno": None,
            "rank": None,
            "tournament_name": None,
        }

        # Use whole_file instead of hand_text for XML parsing
        xml_source = getattr(self, "whole_file", hand_text)

        # Parse tournament info from XML - extended patterns
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

            # Extended data for tournament results
            "rewarddrawn": r"<rewarddrawn>([^<]*)</rewarddrawn>",
            "statuspoints": r"<statuspoints>([^<]*)</statuspoints>",
            "awardpoints": r"<awardpoints>([^<]*)</awardpoints>",
            "ipoints": r"<ipoints>([^<]*)</ipoints>",
            "gamecount": r"<gamecount>([^<]*)</gamecount>",
            "duration": r"<duration>([^<]*)</duration>",
            "tablesize": r"<tablesize>([^<]*)</tablesize>",
            "mode": r"<mode>([^<]*)</mode>",
            "bets": r"<bets>([^<]*)</bets>",
            "wins": r"<wins>([^<]*)</wins>",
            "chipsin": r"<chipsin>([^<]*)</chipsin>",
            "chipsout": r"<chipsout>([^<]*)</chipsout>",
        }

        tourney_info = {}
        for key, pattern in tourney_patterns.items():
            match = re.search(pattern, xml_source)
            if match:
                tourney_info[key] = match.group(1)
                log.debug("Found tournament %s: %s", key, match.group(1))

        # Extract tournament data
        tournament_data["tourno"] = tourney_info.get("tournamentcode")
        tournament_data["tournament_name"] = tourney_info.get("tournamentname")
        tournament_data["rank"] = tourney_info.get("place")
        tournament_data["currency_symbol"] = tourney_info.get("currency", "EUR")

        # Extended tournament data
        tournament_data["gamecount"] = tourney_info.get("gamecount", "0")
        tournament_data["duration"] = tourney_info.get("duration", "")
        tournament_data["tablesize"] = tourney_info.get("tablesize", "")
        tournament_data["mode"] = tourney_info.get("mode", "")
        tournament_data["statuspoints"] = tourney_info.get("statuspoints", "0")
        tournament_data["awardpoints"] = tourney_info.get("awardpoints", "0")
        tournament_data["ipoints"] = tourney_info.get("ipoints", "0")
        tournament_data["bets"] = tourney_info.get("bets", "0")
        tournament_data["wins"] = tourney_info.get("wins", "0")
        tournament_data["chipsin"] = tourney_info.get("chipsin", "0")
        tournament_data["chipsout"] = tourney_info.get("chipsout", "0")

        # Parse buyin amounts
        try:
            buyin_str = tourney_info.get("buyin", "0")
            if buyin_str and buyin_str != "0":
                buyin_clean = self._clean_currency_amount(buyin_str)
                tournament_data["buyin_amount"] = Decimal(buyin_clean)

            birake_str = tourney_info.get("birake", "0")
            if birake_str and birake_str != "0":
                birake_clean = self._clean_currency_amount(birake_str)
                tournament_data["fee_amount"] = Decimal(birake_clean)

            totalbuyin_str = tourney_info.get("totalbuyin", "0")
            if totalbuyin_str and totalbuyin_str != "0":
                totalbuyin_clean = self._clean_currency_amount(totalbuyin_str)
                tournament_data["totbuyin_amount"] = Decimal(totalbuyin_clean)

            # Parse hero winnings
            win_str = tourney_info.get("win", "0")
            if win_str and win_str != "0":
                win_clean = self._clean_currency_amount(win_str)
                tournament_data["hero_winnings"] = Decimal(win_clean)
            else:
                tournament_data["hero_winnings"] = Decimal("0")

            # Parse reward drawn (Twister prize pool)
            rewarddrawn_str = tourney_info.get("rewarddrawn", "0")
            if rewarddrawn_str and rewarddrawn_str != "0":
                reward_clean = self._clean_currency_amount(rewarddrawn_str)
                tournament_data["rewarddrawn"] = Decimal(reward_clean)
            else:
                tournament_data["rewarddrawn"] = Decimal("0")

            # Calculate Twister multiplier (rewarddrawn / buyin)
            if tournament_data["rewarddrawn"] > 0 and tournament_data["buyin_amount"] > 0:
                tournament_data["multiplier"] = tournament_data["rewarddrawn"] / tournament_data["buyin_amount"]
                log.debug("Calculated Twister multiplier: %s (rewarddrawn: %s / buyin: %s)",
                         tournament_data["multiplier"], tournament_data["rewarddrawn"], tournament_data["buyin_amount"])
            elif tournament_data["rewarddrawn"] > 0 and tournament_data["totbuyin_amount"] > 0:
                # Fallback to totalbuyin if buyin_amount is 0
                tournament_data["multiplier"] = tournament_data["rewarddrawn"] / tournament_data["totbuyin_amount"]
                log.debug("Calculated Twister multiplier using totalbuyin: %s (rewarddrawn: %s / totalbuyin: %s)",
                         tournament_data["multiplier"], tournament_data["rewarddrawn"],
                         tournament_data["totbuyin_amount"])
            else:
                tournament_data["multiplier"] = Decimal("0")
                log.debug("Cannot calculate multiplier: rewarddrawn=%s, buyin_amount=%s, totbuyin_amount=%s",
                         tournament_data["rewarddrawn"], tournament_data["buyin_amount"],
                         tournament_data["totbuyin_amount"])

        except (ValueError, TypeError, decimal.InvalidOperation) as e:
            log.warning("Error parsing tournament buyin amounts: %s", e)

        self._validate_tournament_data(tournament_data)
        return tournament_data

    def _extract_tournament_data_from_match(self, mg: dict, tournament_data: dict) -> None:
        """Extract tournament data from regex match."""
        if mg.get("TOURNO"):
            tournament_data["tourno"] = mg["TOURNO"]
            log.debug("Parsed tournament number: %s", tournament_data["tourno"])

        if mg.get("NAME"):
            tournament_data["tournament_name"] = mg["NAME"]
            log.debug("Parsed tournament name: %s", tournament_data["tournament_name"])

        if mg.get("PLACE"):
            tournament_data["rank"] = mg["PLACE"]
            log.debug("Parsed tournament place: %s", tournament_data["rank"])

        self._process_buyin_amount(mg, tournament_data)
        self._process_fee_amounts(mg, tournament_data)
        self._process_total_buyin(mg, tournament_data)

    def _process_buyin_amount(self, mg: dict, tournament_data: dict) -> None:
        """Process buy-in amount from match groups."""
        if mg.get("BIAMT"):
            amt_str = mg["BIAMT"].strip()
            log.debug("Raw BIAMT value: %s", amt_str)
            amt_str = amt_str.replace(",", ".")
            amt_str = self.clearMoneyString(amt_str)

            try:
                if amt_str:
                    tournament_data["buyin_amount"] = Decimal(amt_str)
                    log.debug("Converted BIAMT to Decimal: %s", tournament_data["buyin_amount"])
                else:
                    log.warning("Empty or invalid BIAMT value: %s", mg["BIAMT"])
            except InvalidOperation:
                log.exception("Failed to convert BIAMT to Decimal: %s", amt_str)
                tournament_data["buyin_amount"] = Decimal("0")

    def _process_fee_amounts(self, mg: dict, tournament_data: dict) -> None:
        """Process fee amounts (BIRAKE and BIRAKE2) from match groups."""
        if mg.get("BIRAKE"):
            rake_str = mg["BIRAKE"].strip().replace(",", ".")
            rake_str = self.clearMoneyString(rake_str)
            try:
                if rake_str:
                    tournament_data["fee_amount"] = Decimal(rake_str)
                    log.debug("Converted BIRAKE to Decimal: %s", tournament_data["fee_amount"])
            except InvalidOperation:
                log.exception("Failed to convert BIRAKE to Decimal: %s", rake_str)

        if mg.get("BIRAKE2"):
            rake2_str = mg["BIRAKE2"].strip().replace(",", ".")
            rake2_str = self.clearMoneyString(rake2_str)
            try:
                if rake2_str:
                    tournament_data["fee_amount"] += Decimal(rake2_str)
                    log.debug("Added BIRAKE2 to fee_amount. New fee_amount: %s", tournament_data["fee_amount"])
            except InvalidOperation:
                log.exception("Failed to convert BIRAKE2 to Decimal: %s", rake2_str)

    def _process_total_buyin(self, mg: dict, tournament_data: dict) -> None:
        """Process total buy-in amount from match groups."""
        if mg.get("TOTBUYIN"):
            totbuy_str = mg["TOTBUYIN"].strip().replace(",", ".")
            totbuy_str = self.clearMoneyString(totbuy_str.replace("€", ""))
            try:
                if totbuy_str:
                    tournament_data["totbuyin_amount"] = Decimal(totbuy_str)
                    log.debug("Converted TOTBUYIN to Decimal: %s", tournament_data["totbuyin_amount"])
            except InvalidOperation:
                log.exception("Failed to convert TOTBUYIN to Decimal: %s", totbuy_str)

    def _validate_tournament_data(self, tournament_data: dict) -> None:
        """Validate and adjust tournament data."""
        if (
            tournament_data["totbuyin_amount"] > 0
            and tournament_data["buyin_amount"] == 0
            and tournament_data["fee_amount"] == 0
        ):
            tournament_data["buyin_amount"] = tournament_data["totbuyin_amount"]
            tournament_data["fee_amount"] = Decimal("0")
            log.debug("Using TOTBUYIN as buy-in amount since BIAMT and fees were missing.")

    def _set_tournament_attributes(self, tournament_data: dict, hand: Any) -> None:
        """Set tournament attributes from parsed data."""
        hand.tourNo = tournament_data["tourno"]
        hand.buyin = int(tournament_data["buyin_amount"] * 100)
        hand.fee = int(tournament_data["fee_amount"] * 100)
        hand.buyinCurrency = tournament_data["currency_symbol"]
        hand.currency = tournament_data["currency_symbol"]
        hand.isTournament = True
        hand.tourneyName = tournament_data["tournament_name"] if tournament_data["tournament_name"] else hand.tablename
        hand.isSng = True
        hand.isRebuy = False
        hand.isAddOn = False
        hand.isKO = False

        # Extended tournament attributes
        hand.gamecount = tournament_data.get("gamecount", "0")
        hand.duration = tournament_data.get("duration", "")
        hand.tablesize = tournament_data.get("tablesize", "")
        hand.mode = tournament_data.get("mode", "")

        # iPoker points
        hand.statuspoints = tournament_data.get("statuspoints", "0")
        hand.awardpoints = tournament_data.get("awardpoints", "0")
        hand.ipoints = tournament_data.get("ipoints", "0")

        # Player performance
        hand.bets = tournament_data.get("bets", "0")
        hand.wins = tournament_data.get("wins", "0")
        hand.chipsin = tournament_data.get("chipsin", "0")
        hand.chipsout = tournament_data.get("chipsout", "0")

        # Hero winnings (in cents)
        hand.hero_winnings = int(tournament_data.get("hero_winnings", Decimal("0")) * 100)

        # Reward drawn (Twister prize pool) in cents
        hand.rewarddrawn = int(tournament_data.get("rewarddrawn", Decimal("0")) * 100)

        # Twister multiplier (rewarddrawn / buyin)
        hand.multiplier = float(tournament_data.get("multiplier", Decimal("0")))

        # Lottery tournament detection and attributes
        hand.isLottery = tournament_data.get("multiplier", Decimal("0")) > 1
        hand.tourneyMultiplier = int(tournament_data.get("multiplier", Decimal("1")))

        if not hasattr(hand, "endTime"):
            hand.endTime = hand.startTime

        log.debug("Set tournament attributes: tourNo=%s, buyin=%s, fee=%s",
                 hand.tourNo, hand.buyin, hand.fee)
        log.debug("Set tournament attributes continued: hero_winnings=%s, rewarddrawn=%s, multiplier=%s",
                 hand.hero_winnings,
                 hand.rewarddrawn, hand.multiplier)

    def _process_tournament_players(self, hand: Any, tournament_data: dict) -> None:
        """Process tournament players and their results."""
        # Initialize player data
        for player in hand.players:
            player_name = player[1]
            hand.playersIn.append(player_name)
            hand.ranks[player_name] = 0
            hand.winnings[player_name] = 0

        # Set rank for specific player if available
        if tournament_data["rank"] and tournament_data["rank"] != "N/A":
            try:
                rank_value = int(tournament_data["rank"])
                if hasattr(self, 'hero') and self.hero and self.hero in hand.ranks:
                    hand.ranks[self.hero] = rank_value
                    log.debug("Set rank for hero %s: %s", self.hero, rank_value)
            except (ValueError, TypeError):
                log.warning("Invalid rank value: %s", tournament_data["rank"])

        # Set hero winnings from tournament data
        if hasattr(self, 'hero') and self.hero and self.hero in hand.winnings:
            hero_winnings_cents = int(tournament_data.get("hero_winnings", Decimal("0")) * 100)
            hand.winnings[self.hero] = hero_winnings_cents
            log.debug("Set winnings for hero %s: %s cents", self.hero, hero_winnings_cents)
        else:
            log.error("Hero %s not found in hand.winnings: %s", getattr(self, 'hero', 'None'), hand.winnings)

        # For Twister tournaments, calculate other players' winnings based on Twister rules
        if tournament_data.get("multiplier", Decimal("0")) > 1:
            # In Twister, only the winner gets the prize pool, others get 0
            if hasattr(self, 'hero') and self.hero and self.hero in hand.ranks and hand.ranks[self.hero] == 1:
                # Hero is the winner, already set above
                pass
            elif hasattr(self, 'hero') and self.hero and self.hero in hand.winnings:
                hand.winnings[self.hero] = 0
                log.debug("Set winnings for hero %s to 0 (non-winner in Twister)", self.hero)

        # Set hand statistics
        hand.entries = len(hand.playersIn)
        hand.prizepool = sum(hand.winnings.values())

        # Tournament summary will be handled by iPokerSummary parser automatically
        # when summary_in_file = True and summaryImporter="iPokerSummary" in config
        log.debug("Tournament summary will be processed by iPokerSummary parser")

    def _create_tournament_summary(self, hand: Any) -> None:
        """Create and save tournament summary."""
        try:
            if not hasattr(self, "db"):
                self.db = Database.Database(self.config)
                log.debug("Initialized database connection")

            summary = TourneySummary(
                db=self.db,
                config=self.config,
                siteName=self.sitename,
                summaryText=hand.handText,
                builtFrom="HHC",
                header="",
            )

            # Set summary attributes
            summary.tourNo = hand.tourNo
            summary.buyin = hand.buyin
            summary.fee = hand.fee
            summary.buyinCurrency = hand.buyinCurrency
            summary.currency = hand.buyinCurrency
            summary.startTime = hand.startTime
            summary.endTime = hand.endTime
            summary.gametype = hand.gametype
            summary.maxseats = hand.maxseats
            summary.entries = hand.entries
            summary.speed = "Normal"
            summary.isSng = hand.isSng
            summary.isRebuy = hand.isRebuy
            summary.isAddOn = hand.isAddOn
            summary.isKO = hand.isKO

            # Add players to summary
            for pname, rank in hand.ranks.items():
                winnings = hand.winnings.get(pname, Decimal("0"))
                summary.addPlayer(
                    rank=rank,
                    name=pname,
                    winnings=int(winnings * 100),
                    winningsCurrency=hand.buyinCurrency,
                    rebuyCount=0,
                    addOnCount=0,
                    koCount=0,
                )

            summary.insertOrUpdate()
            log.debug("Tournament summary saved: entries=%s, prizepool=%s", hand.entries, hand.prizepool)

        except Exception:
            log.exception("Error processing tournament summary")

    @staticmethod
    def getTableTitleRe(
        game_type: str,
        table_name: str | None = None,
        tournament: str | None = None,
        table_number: int | None = None,
    ) -> str:
        """Generate a regular expression pattern for table title.

        Args:
            game_type: A string value.
            table_name: A string value representing the table name.
            tournament: A string value representing the tournament.
            table_number: An integer value representing the table number.

        Returns:
            A string value representing the regular expression pattern for table title.
        """
        # Log the input parameters
        log.info("iPoker table_name='%s' tournament='%s' table_number='%s'", table_name, tournament, table_number)

        # Generate the regex pattern based on the input parameters
        regex = str(table_name)

        if game_type == "tour":
            regex = rf"([^\(]+)\s{table_number}"
            log.debug("Generated regex for 'tour': %s", regex)
            return regex
        if table_name.find("(No DP),") != -1:
            regex = table_name.split("(No DP),")[0]
        elif table_name.find(",") != -1:
            regex = table_name.split(",")[0]
        else:
            regex = table_name.split(" ")[0]

        # Log the generated regex pattern and return it
        log.info("iPoker returns: '%s'", regex)
        return regex

    def readOther(self, hand: Any) -> None:
        """Read other information from hand that doesn't fit standard categories."""
        log.debug("Reading other information for hand: %s", hand.handid)
