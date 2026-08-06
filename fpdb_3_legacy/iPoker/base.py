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

# This code is based on CarbonToFpdb.py by Matthew Boss.
#
# The original Carbon converter carried a long list of unimplemented features.
# Most of them have since been implemented for the iPoker XML format:
#   - Tournaments: readSupportedGames() advertises "tour"; tourNo, buyin, fee
#     and buyinCurrency are parsed from the session <general> header
#     (hand_info / xml_format mixins) and surfaced to TourneySummary.
#   - Currency: multi-currency support ($, €, £, RSD, kr, ...) via the LS symbol
#     set and the <currency>/<tablecurrency>/<tournamentcurrency> XML tags -
#     ring games are no longer assumed to be USD.
#   - Antes and bring-in: readAntes() and readBringIn() are implemented, with
#     action types "16" (bring-in) and "7" (all-in) handled in streets_actions.
#   - maxseats: parsed from the <tablesize> XML tag rather than guessed.
#   - All-in in the blinds: handled by the tournament blind fix-up in
#     streets_actions (previously the blocker that made tournaments unparseable).
#   - Hand IDs are stored directly from the <game gamecode="..."> attribute.
#
# Known remaining limitations:
#   - Run-it-twice tables are not supported (iPoker does not expose this).
#   - Tournament game-type detection currently falls back to "ring" when
#     _process_tournament_info() cannot extract the tournament fields; this path
#     lacks end-to-end regression coverage - see the iPoker tournament fixtures
#     under regression-test-files/tour/iPoker/.

from __future__ import annotations

import contextlib
import datetime
import decimal
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

from fpdb_3_legacy import Database
from fpdb_3_legacy.HandHistoryConverter import FpdbParseError, HandHistoryConverter
from fpdb_3_legacy.iPoker.dispatcher import detect_skin, resolve_site_id
from fpdb_3_legacy.iPoker.hand_info import IPokerHandInfoMixin
from fpdb_3_legacy.iPoker.streets_actions import IPokerStreetsActionsMixin
from fpdb_3_legacy.iPoker.tournament_results import IPokerTournamentResultsMixin
from fpdb_3_legacy.iPoker.xml_format import IPokerXMLFormatMixin
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.TourneySummary import TourneySummary

log = get_logger("ipoker_parser")


class iPoker(IPokerStreetsActionsMixin, IPokerHandInfoMixin, IPokerTournamentResultsMixin, IPokerXMLFormatMixin, HandHistoryConverter):  # noqa: N801
    """A class for converting iPoker hand history files to the PokerTH format."""

    tinfo: dict[str, Any]

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
    # Anchored on gamecode: a bare code="..." also matches the enclosing
    # <session sessioncode="..."> tag, so the first hand of every file took the
    # session code as its hand id instead of its own gamecode.
    re_hand_info = re.compile(
        r'gamecode="(?P<HID>[0-9]+)".*?<general>(.*?<startdate>(?P<DATETIME>[\.a-zA-Z-/: 0-9]+)</startdate>)?',
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
    # Enhanced re_Action pattern to handle both Betclic and FDJ formats
    # Supports both "sum="0€"" and "sum="€0.02"" formats with flexible attribute order
    # Also handles both comma (0,02€) and dot (0.02€) decimal separators
    re_action = re.compile(
        r'<action(?=(?:[^>]*\bno="(?P<ACT>\d+)"))(?=(?:[^>]*\bplayer="(?P<PNAME>[^"]+)"))(?=(?:[^>]*\btype="(?P<ATYPE>\d+)"))(?=(?:[^>]*\bsum="[^"]*?(?P<BET>\d+(?:[.,]\d+)?)[^"]*"))[^>]*>',
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
    # Newer exports name the table "Hyper Turbo (500 Chips) (#16727068)" instead
    # of ending it with ", 16727068".
    re_tour_no_hash = re.compile(r"\(#(?P<TOURNO>\d+)\)")
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Build the converter and pin its skin identity to the input path.

        The skin follows from the path, so resolve it now instead of waiting for
        determineGameType(): that is the only other caller, and it never runs on a
        pass that parses no hands. The converter kept the site name the Importer
        passed in -- the one that owns the watched directory in the config -- so an
        import of a PMU file was reported as "Redbet Poker" whenever it turned up
        no new hands. A path that identifies no skin keeps the configured name.
        """
        super().__init__(*args, **kwargs)
        skin_path = self._skin_detection_path()
        if skin_path and self.detectSkin(skin_path) != "iPoker":
            self._apply_skin_from_input_path()

    def detectSkin(self, path: str) -> str:
        """Detect the iPoker skin from the file path."""
        return detect_skin(path)

    def _input_path(self) -> str:
        """Return the parser input path used by skin-specific hooks."""
        return getattr(self, "in_path", "") or ""

    def _file_creation_time_path(self) -> Path | None:
        """Return the filesystem path used for file timestamp fallback."""
        input_path = self._input_path()
        if input_path and input_path != "-":
            return Path(input_path)
        return None

    def _filename_game_info_source(self) -> str:
        """Return the filename/path source used by game-info fallback parsing."""
        return self._input_path()

    def _skin_detection_path(self) -> str:
        """Return the path string used to resolve iPoker skin identity."""
        return self._input_path()

    def _apply_skin_from_input_path(self) -> None:
        """Resolve skin and site id from the current input path."""
        skin_path = self._skin_detection_path()
        if not skin_path:
            return

        detected_skin = self.detectSkin(skin_path)
        self.sitename = detected_skin
        site_id_result = resolve_site_id(self.config, self.sitename)
        if site_id_result:
            self.site_id = site_id_result
            log.debug("Set site_id to %s for skin %s", self.site_id, self.sitename)
            return

        log.warning("Could not find site ID for %s, using default iPoker ID", self.sitename)
        self.sitename = "iPoker"
        self.site_id = 14

    def _summary_site_name(self) -> str:
        """Return the site name used when building tournament summaries."""
        return self.sitename

    def getFileCreationTime(self) -> datetime.datetime:
        """Get the creation time of the current hand history file.

        Returns:
            datetime: File creation time or current time if file doesn't exist
        """
        try:
            file_path = self._file_creation_time_path()
            if file_path is not None and file_path.exists():
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

    def parseHeader(self, hand_text: str, whole_file: str) -> dict[str, Any]:
        """Parses the header of a hand history and returns the game type.

        Args:
            hand_text (str): The text containing the header of the hand history.
            whole_file (str): The entire text of the hand history.

        Returns:
            The parsed game-type mapping.

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
        if not m2 and hasattr(self, "whole_file") and self.whole_file:
            m2 = self.re_max_seats.search(self.whole_file)
            if m2:
                log.debug("re_max_seats regex matched in whole_file.")

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

    def _create_tournament_summary_with_all_players(self, hand: Any, tournament_data: dict) -> None:  # noqa: C901, PLR0912, PLR0915
        """Create a TourneySummary with all players parsed from XML."""
        db = None
        try:
            from decimal import Decimal

            from fpdb_3_legacy.Database import Database
            from fpdb_3_legacy.TourneySummary import TourneySummary

            log.info("Creating TourneySummary with all players")

            # Get database connection
            db = Database(self.config)

            # Create TourneySummary
            summary = TourneySummary(
                db=db,
                config=self.config,
                siteName=self._summary_site_name(),
                summaryText=getattr(self, "whole_file", hand.handText),
                builtFrom="HHC",
                header="",
            )

            # Set basic tournament info
            summary.tourNo = tournament_data.get("tourno")
            summary.tourneyName = tournament_data.get("tournament_name", "Unknown")
            summary.buyin = int(tournament_data.get("buyin_amount", Decimal(0)) * 100)
            summary.fee = int(tournament_data.get("fee_amount", Decimal(0)) * 100)
            summary.buyinCurrency = tournament_data.get("currency_symbol", "EUR")
            summary.currency = summary.buyinCurrency

            # TourneyTypes.category/limitType are NOT NULL. Left at the
            # TourneySummary defaults (None) the insert failed with
            # "Column 'category' cannot be null" on MySQL/PostgreSQL, and the
            # error escaped this method and killed the parse of the hand itself,
            # so iPoker tournament hands could not be imported at all. The hand
            # being parsed already carries both.
            summary.gametype["category"] = hand.gametype.get("category")
            summary.gametype["limitType"] = hand.gametype.get("limitType")
            summary.gametype["mix"] = hand.gametype.get("mix") or "none"
            if not summary.gametype["category"] or not summary.gametype["limitType"]:
                log.warning(
                    "Not storing the tournament summary of %s: unknown game category/limit (%s)",
                    summary.tourNo,
                    hand.gametype,
                )
                return

            # Parse tournament data from session/general (not game/players)
            xml_source = getattr(self, "whole_file", hand.handText)

            # Get hero data from session/general
            hero_name_match = re.search(r"<nickname>([^<]*)</nickname>", xml_source)
            hero_place = re.search(r"<place>([^<]*)</place>", xml_source)
            hero_win = re.search(r"<win>([^<]*)</win>", xml_source)

            if hero_name_match:
                hero_name = hero_name_match.group(1)

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
                            multiplier = rewarddrawn / (Decimal(summary.buyin) / Decimal(100))
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

        except Exception:  # noqa: BLE001 - storing the summary must never fail the hand
            # Anything the database rejects (constraint, connection, schema) is a
            # problem with the summary alone: the hand itself parsed fine and
            # still has to be importable.
            log.exception("Error creating TourneySummary")
        finally:
            # Opened above just for this write; without closing, every imported
            # tournament file left a connection behind.
            if db is not None:
                with contextlib.suppress(Exception):
                    db.close_connection()

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
        table = mg.get("TABLE", "") or ""
        mt = self.re_tour_no.search(table)
        if mt:
            self.tinfo["tourNo"] = mt.group("TOURNO")
            log.debug("Set tourNo from re_tour_no: %s", self.tinfo["tourNo"])
            return True

        # fallback if re_tour_no not matched
        tour_no = table.split(",")[-1].strip().split(" ")[0]
        if tour_no.isdigit():
            self.tinfo["tourNo"] = tour_no
            log.debug("Set tourNo from split TABLE: %s", tour_no)
            return True

        # Newer format, where the number is parenthesised inside the name.
        # Without this the number was never found, _process_tournament_info gave
        # up, and the hand fell through to the ring-game path: a sit'n'go
        # imported as a cash hand.
        hashed = self.re_tour_no_hash.search(table)
        if hashed:
            self.tinfo["tourNo"] = hashed.group("TOURNO")
            log.debug("Set tourNo from parenthesised TABLE number: %s", self.tinfo["tourNo"])
            return True

        log.error("Failed to parse tourNo from TABLE.")
        return False

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

        # Fallbacks for the common iPoker layout that has no <tournamentcode> tag
        # and whose <totalbuyin> only matches the permissive re_buyin pattern:
        #   - tourNo is already parsed from the table name by
        #     _extract_tournament_number (stored in self.tinfo),
        #   - the total buy-in can still be read with re_buyin.
        # Without these, tournaments were misdetected as ring games.
        if not mg.get("TOURNO"):
            mg["TOURNO"] = self.tinfo.get("tourNo")
        if not mg.get("TOTBUYIN"):
            total_buyin_match = self.re_buyin.search(hand_text)
            if total_buyin_match:
                mg["TOTBUYIN"] = total_buyin_match.group("TOTBUYIN")

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

        # Check essential info. TOTBUYIN is intentionally not required: this method
        # is only reached once the hand is already known to be a tournament (a
        # <tournamentname>/<place> was found), and satellites/reward entries can
        # have an empty <totalbuyin>. The buy-in amount is resolved separately by
        # _process_buyin_info (defaulting to FREE/0), so its absence must not
        # demote a genuine tournament back to a ring game.
        if not mg.get("TOURNO") or not mg.get("NAME") or not mg.get("PLACE"):
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
        self._apply_skin_from_input_path()

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

    def _create_tournament_summary(self, hand: Any) -> None:
        """Create and save tournament summary."""
        try:
            if not hasattr(self, "db"):
                self.db = Database.Database(self.config)
                log.debug("Initialized database connection")

            summary = TourneySummary(
                db=self.db,
                config=self.config,
                siteName=self._summary_site_name(),
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
                winnings = hand.winnings.get(pname, Decimal(0))
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
        tourney_name: str | None = None,
    ) -> str:
        """Generate a regular expression pattern for table title.

        Args:
            game_type: A string value.
            table_name: A string value representing the table name.
            tournament: A string value representing the tournament.
            table_number: An integer value representing the table number.
            tourney_name: A string value representing the tournament name.

        Returns:
            A string value representing the regular expression pattern for table title.
        """
        # Log the input parameters
        log.info(
            "iPoker table_name='%s' tournament='%s' table_number='%s' tourney_name='%s'",
            table_name,
            tournament,
            table_number,
            tourney_name,
        )

        # Generate the regex pattern based on the input parameters
        normalized_table_name = table_name or ""

        # Clean common iPoker prefixes (like "100BB", "50BB", "20-50BB", etc.)
        # that are present in the XML hand history but missing from the window title
        clean_table_name = re.sub(
            r'^(?:\d+(?:-\d+)?\s*BB|Deep|Speed|Turbo|Ante|Shallow|Cap|DoublePay|No DP)\s+',
            '',
            normalized_table_name,
            flags=re.IGNORECASE
        )

        if game_type == "tour":
            is_twister = False
            # Check if this is a Twister tournament
            if tourney_name and "twister" in tourney_name.lower():
                is_twister = True
            elif table_name and "twister" in table_name.lower():
                is_twister = True
            elif tournament and "twister" in str(tournament).lower():
                is_twister = True

            if is_twister:
                # Twister tables don't have table numbers in the window title, they are named "Twister" or "Spins"
                # We return a regex matching either Twister or Spins (branded on some French skins like Bwin.fr/PMU)
                regex = r"(?:Twister|Spins)"
                log.debug("Generated regex for Twister/Spins SNG: %s", regex)
                return regex

            # A hand history only carries a table number when the tableName ends
            # in one ("<no> <name>, <tableNo>"); without it TableWindow falls back
            # to the tournament number, which never appears in the window title.
            # Match on the tournament name instead, as it does.
            if table_number is None or str(table_number) == str(tournament):
                title_name = tourney_name or clean_table_name
                regex = re.escape(title_name) if title_name else ""
                log.debug("Generated name regex for 'tour' without table number: %s", regex)
                return regex

            regex = rf"([^\(]+)\s{table_number}"
            log.debug("Generated regex for 'tour': %s", regex)
            return regex
        if clean_table_name.find("(No DP),") != -1:
            regex = clean_table_name.split("(No DP),")[0]
        elif clean_table_name.find(",") != -1:
            regex = clean_table_name.split(",")[0]
        else:
            regex = clean_table_name.split(" ")[0]

        # Escape to ensure it is treated as a literal pattern
        regex = re.escape(regex)

        # Log the generated regex pattern and return it
        log.info("iPoker returns: '%s'", regex)
        return regex

    def readOther(self, hand: Any) -> None:
        """Read other information from hand that doesn't fit standard categories."""
        log.debug("Reading other information for hand: %s", hand.handid)
