"""Winamx poker hand history parser for FPDB."""

#    Copyright 2008-2011, Carl Gherardi
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

import datetime
import platform
import re
from collections.abc import Callable
from decimal import Decimal
from re import Match
from typing import TYPE_CHECKING, Any, ClassVar

from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger

if TYPE_CHECKING:
    from Hand import Hand

# Winamax HH Format
log = get_logger("winamax_parser")


class Winamax(HandHistoryConverter):
    """Parses Winamax poker hand histories for FPDB.

    This class provides methods to extract game, player, and hand information from Winamax hand history text. It supports parsing various game types, extracting player actions, blinds, community cards, and tournament details, and converting them into a standardized format for further processing.
    """

    EXPECTED_SUMMARY_PARTS = 2
    MIN_PLAYERS = 2
    STUD_HOLE_CARDS_COUNT = 3

    def Trace(self) -> Callable[..., Any]:
        """Decorator that logs function entry and exit for debugging purposes.

        Returns:
            A wrapped function that logs entry/exit and preserves original behavior.
        """

        def my_f(*args: Any, **kwds: Any) -> Any:
            log.debug("entering %s", self.__class__.__name__)
            result = self(*args, **kwds)
            log.debug("exiting %s", self.__class__.__name__)
            return result

        my_f.__name__ = self.__class__.__name__
        my_f.__doc__ = self.__doc__
        return my_f

    filter = "Winamax"
    sitename = "Winamax"
    filetype = "text"
    codepage = ("utf8", "cp1252")
    site_id = 15  # Needs to match id entry in Sites database

    mixes: ClassVar = {
        "8games": "8game",
        "10games": "10game",
        "horse": "horse",
    }  # Legal mixed games
    sym: ClassVar = {
        "USD": r"\$",
        "CAD": r"\$",
        "T$": "",
        "EUR": "\xe2\x82\xac|\u20ac",
        "GBP": "\xa3",
        "play": "",
    }
    # ADD Euro, Sterling, etc HERE
    substitutions: ClassVar[dict[str, str]] = {
        "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP",  # legal ISO currency codes
        "LS": "\\$|\xe2\x82\xac|\u20ac|",  # legal currency symbols - Euro(cp1252, utf-8)
    }

    limits: ClassVar[dict[str, str]] = {"no limit": "nl", "pot limit": "pl", "fixed limit": "fl"}

    games: ClassVar[dict[str, tuple[str, str]]] = {  # base, category
        "Holdem": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha5": ("hold", "5_omahahi"),
        "5 Card Omaha": ("hold", "5_omahahi"),
        "5 Card Omaha Hi/Lo": ("hold", "5_omahahi"),  # incorrect in file
        "Omaha Hi/Lo": ("hold", "omahahilo"),
        "Omaha8": ("hold", "omahahilo"),
        "7-Card Stud": ("stud", "studhi"),
        "7stud": ("stud", "studhi"),
        "7-Card Stud Hi/Lo": ("stud", "studhilo"),
        "7stud8": ("stud", "studhilo"),
        "Razz": ("stud", "razz"),
        "2-7 Triple Draw": ("draw", "27_3draw"),
        "Lowball27": ("draw", "27_3draw"),
    }

    # Static regexes
    # ***** End of hand R5-75443872-57 *****
    re_identify = re.compile(
        r'Winamax\sPoker\s\-\s(CashGame|Go\sFast|HOLD\-UP|ESCAPE|Tournament\s")',
    )
    re_split_hands = re.compile(r"\n\n")

    re_hand_info = re.compile(
        """
            \\s*Winamax\\sPoker\\s-\\s
            (?P<RING>(CashGame|Go\\sFast\\s"[^"]+"|HOLD\\-UP\\s"[^"]+"|ESCAPE\\s"[^"]+"))?
            (?P<TOUR>Tournament\\s
            (?P<TOURNAME>.+)?\\s
            buyIn:\\s(?P<BUYIN>(?P<BIAMT>[\\d\\,.]+)({LS})?\\s?\\+?\\s?(?P<BIRAKE>[\\d\\,.]+)({LS})?\\+?(?P<BOUNTY>[{LS}\\d\\.]+)?\\s?(?P<TOUR_ISO>{LEGAL_ISO})?|(?P<FREETICKET>[\\sa-zA-Z]+))?\\s
            (level:\\s(?P<LEVEL>\\d+))?
            .*)?
            \\s-\\sHandId:\\s\\#(?P<HID1>\\d+)-(?P<HID2>\\d+)-(?P<HID3>\\d+)\\s-\\s  # REB says: HID3 is the correct
            # hand number
            (?P<GAME>Holdem|Omaha|Omaha5|Omaha8|5\\sCard\\sOmaha|5\\sCard\\sOmaha\\sHi/Lo|Omaha\\sHi/Lo|7\\-Card\\sStud|7stud|7\\-Card\\sStud\\sHi/Lo|7stud8|Razz|2\\-7\\sTriple\\sDraw|Lowball27)\\s
            (?P<LIMIT>fixed\\slimit|no\\slimit|pot\\slimit)\\s
            \\(
            ((({LS})?(?P<ANTE>[.0-9]+)({LS})?)/)?
            (({LS})?(?P<SB>[.0-9]+)({LS})?)/
            (({LS})?(?P<BB>[.0-9]+)({LS})?)
            \\)\\s-\\s
            (?P<DATETIME>.*)
            Table:?\\s\'(?P<TABLE>[^(]+)
            (.(?P<TOURNO>\\d+).\\#(?P<TABLENO>\\d+))?.*
            \'
            \\s(?P<MAXPLAYER>\\d+)\\-max
            \\s(?P<MONEY>\\(real\\smoney\\))?
            """.format(**substitutions),
        re.MULTILINE | re.DOTALL | re.VERBOSE,
    )

    re_tail_split_hands = re.compile(r"\n\s*\n")
    re_button = re.compile(r"Seat\s#(?P<BUTTON>\d+)\sis\sthe\sbutton")
    re_board = re.compile(r"\[(?P<CARDS>.+)\]")
    re_total = re.compile(
        r"Total pot (?P<TOTAL>[\.\d]+).*(No rake|Rake (?P<RAKE>[\.\d]+))".format(),
    )
    re_mixed = re.compile(r"_(?P<MIXED>10games|8games|horse)_")
    re_hutp = re.compile(
        r"Hold\-up\sto\sPot:\stotal\s(({LS})?(?P<AMOUNT>[.0-9]+)({LS})?)".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    re_escape_pot = re.compile(
        r"Escape\sto\sPot:\stotal\s(({LS})?(?P<AMOUNT>[.0-9]+)({LS})?)".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    # 2010/09/21 03:10:51 UTC
    re_date_time = re.compile(
        r"""
            (?P<Y>[0-9]{4})/
            (?P<M>[0-9]+)/
            (?P<D>[0-9]+)\s
            (?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)\s
            UTC
            """,
        re.MULTILINE | re.VERBOSE,
    )

    # Seat 1: some_player (5€)
    # Seat 2: some_other_player21 (6.33€)
    # Seat 6: I want fold (147894, 29.25€ bounty)
    re_player_info = re.compile(
        r"Seat\s(?P<SEAT>[0-9]+):\s(?P<PNAME>.*)\s\(({LS})?(?P<CASH>[.0-9]+)({LS})?(,\s({LS})?(?P<BOUNTY>[.0-9]+)({LS})?\sbounty)?\)".format(
            **substitutions,
        ),
    )
    re_player_info_summary = re.compile(
        r"Seat\s(?P<SEAT>[0-9]+):\s(?P<PNAME>.+?)\s".format(),
    )

    def compilePlayerRegexs(self, hand: "Hand") -> None:
        """Compile player-specific regex patterns based on players in the hand.

        Args:
            hand: The Hand object containing player information.
        """
        players = {player[1] for player in hand.players}
        if not players <= self.compiledPlayers:  # x <= y means 'x is subset of y'
            # we need to recompile the player regexs.
            # TODO(fpdb): should probably rename re_hero_cards and corresponding method,
            #    since they are used to find all cards on lines starting with "Dealt to:"
            #    They still identify the hero.
            self.compiledPlayers = players
            # ANTES/BLINDS
            # helander2222 posts blind ($0.25), lopllopl posts blind ($0.50).
            player_re = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"
            subst = {"PLYR": player_re, "CUR": self.sym[hand.gametype["currency"]]}
            self.re_post_sb = re.compile(
                r"{PLYR} posts small blind ({CUR})?(?P<SB>[\.0-9]+)({CUR})?(?! out of position)".format(**subst),
                re.MULTILINE,
            )
            self.re_post_bb = re.compile(
                r"{PLYR} posts big blind ({CUR})?(?P<BB>[\.0-9]+)({CUR})?".format(**subst),
                re.MULTILINE,
            )
            self.re_deny_sb = re.compile("(?P<PNAME>.*) deny SB".format(), re.MULTILINE)
            self.re_antes = re.compile(
                r"^{PLYR} posts ante ({CUR})?(?P<ANTE>[\.0-9]+)({CUR})?".format(**subst),
                re.MULTILINE,
            )
            self.re_bring_in = re.compile(
                r"^{PLYR} (brings in|bring\-in) ({CUR})?(?P<BRINGIN>[\.0-9]+)({CUR})?".format(**subst),
                re.MULTILINE,
            )
            self.re_post_both = re.compile(
                r"(?P<PNAME>.*): posts small \& big blind \( ({CUR})?(?P<SBBB>[\.0-9]+)({CUR})?\)".format(**subst),
            )
            self.re_post_dead = re.compile(
                r"(?P<PNAME>.*) posts dead blind \(({CUR})?(?P<DEAD>[\.0-9]+)({CUR})?\)".format(**subst),
                re.MULTILINE,
            )
            self.re_post_second_sb = re.compile(
                r"{PLYR} posts small blind ({CUR})?(?P<SB>[\.0-9]+)({CUR})? out of position".format(**subst),
                re.MULTILINE,
            )
            self.re_hero_cards = re.compile(
                r"Dealt\sto\s{PLYR}(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(**subst),
            )

            # no discards action observed yet
            self.re_action = re.compile(
                r"(, )?(?P<PNAME>.*?)(?P<ATYPE> bets| checks| raises| calls| folds| stands\spat)"
                r"( \-?({CUR})?(?P<BET>[\d\.]+)({CUR})?)?( to ({CUR})?(?P<BETTO>[\d\.]+)({CUR})?)?"
                r"( and is all-in)?".format(**subst),
            )
            self.re_showdown_action = re.compile(
                "(?P<PNAME>[^\\(\\)\n]*) (\\((small blind|big blind|button)\\) )?shows \\[(?P<CARDS>.+)\\]",
            )

            self.re_collect_pot = re.compile(
                r"\s*(?P<PNAME>.*)\scollected\s({CUR})?(?P<POT>[\.\d]+)({CUR})?.*".format(**subst),
            )
            self.re_shown_cards = re.compile(
                r"^Seat (?P<SEAT>[0-9]+): {PLYR} (\((small blind|big blind|button)\) )?"
                r"showed \[(?P<CARDS>.*)\].+? with (?P<STRING>.*)".format(**subst),
                re.MULTILINE,
            )

    def readSupportedGames(self) -> list[list[str]]:
        """Returns a list of supported game types for Winamax.

        The returned list contains sublists, each representing a supported game type with its format, base, and limit.

        Returns:
            list[list[str]]: A list of supported game type specifications.
        """
        return [
            ["ring", "hold", "fl"],
            ["ring", "hold", "nl"],
            ["ring", "hold", "pl"],
            ["ring", "stud", "fl"],
            ["ring", "draw", "fl"],
            ["ring", "draw", "pl"],
            ["ring", "draw", "nl"],
            ["tour", "hold", "fl"],
            ["tour", "hold", "nl"],
            ["tour", "hold", "pl"],
            ["tour", "stud", "fl"],
            ["tour", "draw", "fl"],
            ["tour", "draw", "pl"],
            ["tour", "draw", "nl"],
        ]

    def _log_parse_error(self, hand_text: str, length: int, message: str) -> None:
        """Logs a parsing error message with a snippet of the hand text.

        This function helps with debugging by logging the provided error message and
        a portion of the hand history text that caused the error.

        Args:
            hand_text (str): The raw hand history text.
            length (int): The number of characters from hand_text to include in the log.
            message (str): The error message to log.

        Returns:
            None
        """
        tmp = hand_text[:length]
        log.error("%s: '%s'", message, tmp)

    def _parse_game_type_info(self, mg: dict[str, str], info: dict[str, Any]) -> None:
        """Parses and updates the game type information from match groups.

        This function examines the match group dictionary to determine if the hand is a tournament or ring game,
        and sets the appropriate type and currency in the info dictionary.

        Args:
            mg (dict[str, str]): The match group dictionary from the hand info regex.
            info (dict[str, Any]): The dictionary to update with game type information.

        Returns:
            None
        """
        if mg.get("TOUR"):
            info["type"] = "tour"
            info["currency"] = "T$"
        elif mg.get("RING"):
            info["type"] = "ring"
            info["currency"] = "EUR" if mg.get("MONEY") else "play"
            info["fast"] = "Go Fast" in mg.get("RING")

    def _parse_limit_info(self, mg: dict[str, str], info: dict[str, Any], hand_text: str) -> None:
        """Parses and updates the limit type information from match groups.

        This function checks the match group dictionary for the limit type and updates the info dictionary accordingly.
        If the limit type is not recognized, it logs an error and raises an exception.

        Args:
            mg (dict[str, str]): The match group dictionary from the hand info regex.
            info (dict[str, Any]): The dictionary to update with limit type information.
            hand_text (str): The raw hand history text for error logging.

        Returns:
            None

        Raises:
            FpdbParseError: If the limit type is not found in the supported limits.
        """
        if "LIMIT" in mg:
            if mg["LIMIT"] in self.limits:
                info["limitType"] = self.limits[mg["LIMIT"]]
            else:
                self._log_parse_error(hand_text, 100, "Limit not found")
                raise FpdbParseError

    def _parse_additional_info(self, mg: dict[str, str], info: dict[str, Any]) -> None:
        """Parses and updates additional game information from match groups.

        This function extracts and sets base game type, category, mix, small blind,
        and big blind information in the info dictionary. It also adjusts blind values for fixed limit games as needed.

        Args:
            mg (dict[str, str]): The match group dictionary from the hand info regex.
            info (dict[str, Any]): The dictionary to update with additional game information.

        Returns:
            None
        """
        if "GAME" in mg:
            (info["base"], info["category"]) = self.games[mg["GAME"]]
        if m := self.re_mixed.search(self.in_path):
            mixed_game = self.mixes[m.groupdict()["MIXED"]]
            info["mix"] = mixed_game
            # For mixed games, base should be "mixed" and category should be the mixed game type
            info["base"] = "mixed"
            info["category"] = mixed_game
        if "SB" in mg:
            info["sb"] = mg["SB"]
        if "BB" in mg:
            info["bb"] = mg["BB"]

        if info.get("limitType") == "fl" and info.get("bb") is not None:
            info["sb"] = str((Decimal(mg["SB"]) / 2).quantize(Decimal("0.01")))
            info["bb"] = str(Decimal(mg["SB"]).quantize(Decimal("0.01")))

    def determineGameType(self, hand_text: str) -> dict[str, Any]:
        """Inspect the hand_text and return the gametype dict.

        Args:
            hand_text: The raw hand history text to parse

        Returns:
            Dict containing game type information with keys like:
            'limitType', 'base', 'category', 'type', 'currency', etc.
        """
        info: dict[str, Any] = {}

        m = self.re_hand_info.search(hand_text)
        if not m:
            self._log_parse_error(hand_text, 200, "determine Game Type failed")
            raise FpdbParseError

        mg = m.groupdict()

        self._parse_game_type_info(mg, info)
        self._parse_limit_info(mg, info, hand_text)
        self._parse_additional_info(mg, info)

        return info

    def readHandInfo(self, hand: "Hand") -> None:
        """Parse and extract hand information from Winamax hand history text.

        Args:
            hand: Hand object to populate with parsed information including handid,
                table name, tournament details, buyin amounts, and timing data.

        Raises:
            FpdbParseError: If hand info regex matching fails.
        """
        info = {}
        m = self.re_hand_info.search(hand.handText)
        if m is None:
            tmp = hand.handText[:200]
            log.error("read Hand Info failed: '%s'", tmp)
            raise FpdbParseError

        info |= m.groupdict()
        log.debug("read Hand Info: %s", info)

        self._process_hand_info_keys(hand, info)
        self._detect_lottery_tournaments(hand, info)
        self._set_mixed_game_type(hand)

    def _process_hand_info_keys(self, hand: "Hand", info: dict) -> None:
        """Processes and dispatches parsed hand info keys to their respective handlers.

        This method iterates over the parsed hand information and calls the appropriate handler function for each key.

        Args:
            hand: The Hand object to update with parsed information.
            info: Dictionary containing parsed hand information.

        """
        for key, value in info.items():
            if handler := self._get_info_handler(key):
                handler(hand, value, info)

    def _get_info_handler(self, key: str) -> callable:
        """Returns the handler function for a given hand info key.

        This method provides a mapping from parsed hand info keys to their corresponding handler functions.

        Args:
            key: The key from the parsed hand information.

        Returns:
            callable: The handler function for the given key, or None if not found.

        """
        handlers = {
            "DATETIME": lambda h, v, i: self._parse_datetime(h, v),  # noqa: ARG005
            "HID1": lambda h, v, i: self._parse_hand_id(h, i),  # noqa: ARG005
            "TOURNO": lambda h, v, i: setattr(h, "tourNo", v),  # noqa: ARG005
            "TABLE": lambda h, v, i: self._parse_table_info(h, v, i),
            "MAXPLAYER": lambda h, v, i: setattr(h, "maxseats", int(v)) if v is not None else None,  # noqa: ARG005
            "BUYIN": lambda h, v, i: self._parse_buyin_info(h, v, i) if i.get("TOURNO") is not None else None,
            "LEVEL": lambda h, v, i: setattr(h, "level", v),  # noqa: ARG005
        }
        return handlers.get(key)

    def _set_mixed_game_type(self, hand: "Hand") -> None:
        """Set mixed game type if this is a mixed game."""
        if hasattr(hand, "gametype") and hand.gametype.get("mix"):
            hand.mixed = hand.gametype["mix"]
        else:
            hand.mixed = None

    def _parse_datetime(self, hand: "Hand", value: str) -> None:
        """Parses and sets the hand's start time from a date-time string.

        This function extracts the date and time from the provided string and
        sets the hand's startTime attribute in UTC. If parsing fails, a default date is used and a warning is logged.

        Args:
            hand (Hand): The Hand object whose start time will be set.
            value (str): The date-time string to parse.

        Returns:
            None
        """
        if a := self.re_date_time.search(value):
            datetimestr = (
                f"{a.group('Y')}/{a.group('M')}/{a.group('D')}" f" {a.group('H')}:{a.group('MIN')}:{a.group('S')}"
            )
        else:
            datetimestr = "2010/Jan/01 01:01:01"
            log.warning("DATETIME not matched: '%s'", value)
        hand.startTime = datetime.datetime.strptime(
            datetimestr,
            "%Y/%m/%d %H:%M:%S",
        ).replace(tzinfo=datetime.timezone.utc)

    def _parse_hand_id(self, hand: "Hand", info: dict) -> None:
        """Parses and sets the hand's unique identifier from parsed info.

        This function constructs the hand ID using the provided info dictionary and assigns it to the hand object.

        Args:
            hand (Hand): The Hand object whose ID will be set.
            info (dict): Dictionary containing hand ID components.

        Returns:
            None
        """
        hand.handid = f"{int(info['HID1'][:14])}{int(info['HID2'])}"

    def _parse_table_info(self, hand: "Hand", value: str, info: dict) -> None:
        """Parses and sets the table information for the hand.

        This function assigns the table name and related properties to the hand object based on the parsed information.
        It handles special cases for tournament tables and standardizes table naming conventions.

        Args:
            hand (Hand): The Hand object whose table information will be set.
            value (str): The table name string to parse.
            info (dict): Dictionary containing additional table information.

        Returns:
            None
        """
        hand.tablename = value
        if hand.gametype["type"] == "tour":
            hand.tablename = info["TABLENO"]
            hand.roundPenny = True
        # TODO(maintainer): long-term solution for table naming on Winamax.
        if hand.tablename.endswith("No Limit Hold'em"):
            hand.tablename = hand.tablename[: -len("No Limit Hold'em")] + "NLHE"

    def _determine_buyin_currency(self, value: str, info: dict) -> str:
        """Determines the currency used for the tournament buy-in.

        This function inspects the buy-in value and related info
        to identify the appropriate currency code for the tournament.

        Args:
            value (str): The buy-in value string to inspect.
            info (dict): Dictionary containing additional tournament information.

        Returns:
            str: The currency code for the buy-in (e.g., 'USD', 'EUR', 'WIFP', or 'play').
        """
        if "$" in value:
            return "USD"
        if "€" in value:
            return "EUR"
        if "FPP" in value or "Free" in value:
            return "WIFP"
        return "EUR" if info["MONEY"] else "play"

    def _process_bounty_info(self, hand: "Hand", info: dict) -> None:
        """Processes and sets bounty information for tournament hands.

        This function updates the hand and info dictionaries to reflect bounty values,
        switching fields as needed and setting KO status.

        Args:
            hand (Hand): The Hand object to update with bounty information.
            info (dict): Dictionary containing bounty and rake information.

        Returns:
            None
        """
        if info["BOUNTY"] is not None:
            # There is a bounty, Which means we need to switch BOUNTY and BIRAKE values
            tmp = info["BOUNTY"]
            info["BOUNTY"] = info["BIRAKE"]
            info["BIRAKE"] = tmp
            info["BOUNTY"] = info["BOUNTY"].strip("$€")
            hand.koBounty = int(100 * Decimal(info["BOUNTY"]))
            hand.isKO = True
        else:
            hand.isKO = False

    def _parse_buyin_info(self, hand: "Hand", value: str, info: dict) -> None:
        """Parses and sets the buy-in and fee information for tournament hands.

        This function processes the buy-in, fee, and currency details from the provided info dictionary and
        updates the hand object accordingly. It handles free tickets, bounty tournaments, and different currency types.

        Args:
            hand (Hand): The Hand object to update with buy-in and fee information.
            value (str): The buy-in value string to parse.
            info (dict): Dictionary containing buy-in, fee, and bounty information.

        Returns:
            None
        """
        log.debug("info['BUYIN']: %s", info["BUYIN"])
        log.debug("info['BIAMT']: %s", info["BIAMT"])
        log.debug("info['BIRAKE']: %s", info["BIRAKE"])
        log.debug("info['BOUNTY']: %s", info["BOUNTY"])

        for k in ["BIAMT", "BIRAKE"]:
            if info.get(k):
                info[k] = info[k].replace(",", ".")

        if info["FREETICKET"] is not None:
            hand.buyin = 0
            hand.fee = 0
            hand.buyinCurrency = "FREE"
        else:
            hand.buyinCurrency = self._determine_buyin_currency(value, info)

            info["BIAMT"] = (
                info["BIAMT"].replace("$", "").replace("€", "").replace("FPP", "") if info["BIAMT"] is not None else 0
            )

            if hand.buyinCurrency != "WIFP":
                self._process_bounty_info(hand, info)
                info["BIRAKE"] = info["BIRAKE"].strip("$€")

                # TODO(maintainer): Is this correct? Old code tried to
                # conditionally multiply by 100, but we
                # want hand.buyin in 100ths of
                # dollars/euros (so hand.buyin = 90 for $0.90 BI).
                hand.buyin = int(100 * Decimal(info["BIAMT"]))
                hand.fee = int(100 * Decimal(info["BIRAKE"]))
            else:
                hand.buyin = int(Decimal(info["BIAMT"]))
                hand.fee = 0

            if hand.buyin == 0 and hand.fee == 0:
                hand.buyinCurrency = "FREE"

    def _detect_lottery_tournaments(self, hand: "Hand", info: dict) -> None:
        """Detects and marks lottery-style tournaments such as Expresso.

        This function checks the tournament name and updates the hand object to indicate
        if it is a lottery tournament, setting the appropriate attributes.

        Args:
            hand (Hand): The Hand object to update with lottery tournament information.
            info (dict): Dictionary containing tournament information.

        Returns:
            None
        """
        if hand.tourNo is not None and info.get("TOURNAME"):
            tourname = info["TOURNAME"].strip('"')
            hand.isLottery = "Expresso" in tourname
            hand.tourneyMultiplier = 1

    def readPlayerStacks(self, hand: "Hand") -> None:
        """Parse player stacks from hand text.

        Splits hand text at summary section and extracts player information
        from the pre-summary section only, as summary may differ if players
        are sitting out.

        Args:
            hand: The Hand object to populate with player information.

        Raises:
            FpdbHandPartial: If hand cannot be split properly or has too few players.
        """
        # Split hand text for Winamax, as the players listed in the hh preamble and the summary will differ
        # if someone is sitting out.
        # Going to parse both and only add players in the summary.
        handsplit = hand.handText.split("*** SUMMARY ***")
        if len(handsplit) != self.EXPECTED_SUMMARY_PARTS:
            msg = f"Hand is not cleanly split into pre and post Summary {hand.handid}."
            raise FpdbHandPartial(
                msg,
            )
        pre = handsplit[0]
        m = self.re_player_info.finditer(pre)
        plist = {}

        # Get list of players in header.
        for a in m:
            if plist.get(a.group("PNAME")) is None:
                hand.addPlayer(int(a.group("SEAT")), a.group("PNAME"), a.group("CASH"))
                plist[a.group("PNAME")] = [int(a.group("SEAT")), a.group("CASH")]

        if len(plist.keys()) < self.MIN_PLAYERS:
            msg = f"Less than {self.MIN_PLAYERS} players in hand! {hand.handid}."
            raise FpdbHandPartial(msg)

    def markStreets(self, hand: "Hand") -> None:
        """Identifies and marks the different streets (betting rounds) in the hand history.

        This function uses regular expressions to extract the text for each street
        (such as preflop, flop, turn, river, etc.) based on the game type,
        and adds them to the hand object for further parsing.

        Args:
            hand (Hand): The Hand object to populate with street information.

        Returns:
            None
        """
        if hand.gametype["base"] == "hold":
            m = re.search(
                r"\*\*\* ANTE/BLINDS \*\*\*(?P<PREFLOP>.+(?=\*\*\* FLOP \*\*\*)|.+)"
                r"(\*\*\* FLOP \*\*\*(?P<FLOP> \[\S\S \S\S \S\S\].+(?=\*\*\* TURN \*\*\*)|.+))?"
                r"(\*\*\* TURN \*\*\* \[\S\S \S\S \S\S](?P<TURN>\[\S\S\].+(?=\*\*\* RIVER \*\*\*)|.+))?"
                r"(\*\*\* RIVER \*\*\* \[\S\S \S\S \S\S \S\S](?P<RIVER>\[\S\S\].+))?",
                hand.handText,
                re.DOTALL,
            )
        elif hand.gametype["base"] == "stud":
            m = re.search(
                r"\*\*\* ANTE/BLINDS \*\*\*(?P<ANTES>.+(?=\*\*\* (3rd STREET|THIRD) \*\*\*)|.+)"
                r"(\*\*\* (3rd STREET|THIRD) \*\*\*(?P<THIRD>.+(?=\*\*\* (4th STREET|FOURTH) \*\*\*)|.+))?"
                r"(\*\*\* (4th STREET|FOURTH) \*\*\*(?P<FOURTH>.+(?=\*\*\* (5th STREET|FIFTH) \*\*\*)|.+))?"
                r"(\*\*\* (5th STREET|FIFTH) \*\*\*(?P<FIFTH>.+(?=\*\*\* (6th STREET|SIXTH) \*\*\*)|.+))?"
                r"(\*\*\* (6th STREET|SIXTH) \*\*\*(?P<SIXTH>.+(?=\*\*\* (7th STREET|SEVENTH) \*\*\*)|.+))?"
                r"(\*\*\* (7th STREET|SEVENTH) \*\*\*(?P<SEVENTH>.+))?",
                hand.handText,
                re.DOTALL,
            )
        else:
            m = re.search(
                r"\*\*\* ANTE/BLINDS \*\*\*(?P<PREDEAL>.+(?=\*\*\* FIRST\-BET \*\*\*)|.+)"
                r"(\*\*\* FIRST\-BET \*\*\*(?P<DEAL>.+(?=\*\*\* FIRST\-DRAW \*\*\*)|.+))?"
                r"(\*\*\* FIRST\-DRAW \*\*\*(?P<DRAWONE>.+(?=\*\*\* SECOND\-DRAW \*\*\*)|.+))?"
                r"(\*\*\* SECOND\-DRAW \*\*\*(?P<DRAWTWO>.+(?=\*\*\* THIRD\-DRAW \*\*\*)|.+))?"
                r"(\*\*\* THIRD\-DRAW \*\*\*(?P<DRAWTHREE>.+))?",
                hand.handText,
                re.DOTALL,
            )

        try:
            hand.addStreets(m)
            log.debug("adding street %s", m.group(0))
            log.debug("---")
        except (AttributeError, TypeError):
            log.info("Failed to add streets. handtext=%s", hand.handtext)

    # Needs to return a list in the format
    # ['player1name', 'player2name', ...] where player1name is the sb and player2name is bb,
    # addtional players are assumed to post a bb oop

    def readButton(self, hand: "Hand") -> None:
        """Parses and sets the dealer button position for the hand.

        This function searches the hand text for the button position and updates the hand object accordingly.
        If the button is not found, it logs an informational message.

        Args:
            hand (Hand): The Hand object to update with button position information.

        Returns:
            None
        """
        if m := self.re_button.search(hand.handText):
            hand.buttonpos = int(m.group("BUTTON"))
            log.debug("read Button: button on pos %s", hand.buttonpos)
        else:
            log.info("read Button: not found")

    def readCommunityCards(
        self,
        hand: "Hand",
        street: str,
    ) -> None:
        """Parses and sets the community cards for the specified street.

        This function extracts the community cards from the hand text for the given street and
        updates the hand object accordingly.

        Args:
            hand (Hand): The Hand object to update with community cards.
            street (str): The street name (e.g., 'FLOP', 'TURN', 'RIVER').

        Returns:
            None
        """
        if street in {"FLOP", "TURN", "RIVER"}:
            # a list of streets which get dealt community cards (i.e. all but PREFLOP)
            m = self.re_board.search(hand.streets[street])
            hand.setCommunityCards(street, m.group("CARDS").split(" "))

    def readBlinds(self, hand: "Hand") -> None:
        """Parses and sets the blinds posted in the hand.

        This function extracts small blind, big blind, dead blind,
        and second small blind postings from the hand text and updates the hand object accordingly.

        Args:
            hand (Hand): The Hand object to update with blind information.

        Returns:
            None
        """
        m = self.re_post_sb.search(hand.handText)
        if m is not None:
            hand.addBlind(m.group("PNAME"), "small blind", m.group("SB"))
        else:
            log.debug("No small blind")
            hand.addBlind(None, None, None)

        for a in self.re_post_bb.finditer(hand.handText):
            hand.addBlind(a.group("PNAME"), "big blind", a.group("BB"))
            amount = Decimal(a.group("BB").replace(",", ""))
            hand.lastBet["PREFLOP"] = amount
        for a in self.re_post_dead.finditer(hand.handText):
            log.debug(
                "Found dead blind: addBlind(%s, 'secondsb', %s)",
                a.group("PNAME"),
                a.group("DEAD"),
            )
            hand.addBlind(a.group("PNAME"), "secondsb", a.group("DEAD"))
        for a in self.re_post_second_sb.finditer(hand.handText):
            log.debug(
                "Found dead blind: addBlind(%s, 'secondsb/both', %s, %s)",
                a.group("PNAME"),
                a.group("SB"),
                hand.sb,
            )
            if Decimal(a.group("SB")) > Decimal(hand.sb):
                hand.addBlind(a.group("PNAME"), "both", a.group("SB"))
            else:
                hand.addBlind(a.group("PNAME"), "secondsb", a.group("SB"))

    def readAntes(self, hand: "Hand") -> None:
        """Parses and sets the antes posted in the hand.

        This function extracts ante postings from the hand text and updates the hand object with each player's ante.

        Args:
            hand (Hand): The Hand object to update with ante information.

        Returns:
            None
        """
        log.debug("reading antes")
        m = self.re_antes.finditer(hand.handText)
        for player in m:
            log.debug("hand add Ante(%s,%s)", player.group("PNAME"), player.group("ANTE"))
            hand.addAnte(player.group("PNAME"), player.group("ANTE"))

    def readBringIn(self, hand: "Hand") -> None:
        """Parses and sets the bring-in bet for stud games.

        This function searches the hand text for a bring-in posting and
        updates the hand object with the player's bring-in amount if found.

        Args:
            hand (Hand): The Hand object to update with bring-in information.

        Returns:
            None
        """
        if m := self.re_bring_in.search(hand.handText, re.DOTALL):
            log.debug("read BringIn: %s for %s", m.group("PNAME"), m.group("BRINGIN"))
            hand.addBringIn(m.group("PNAME"), m.group("BRINGIN"))

    def readSTP(self, hand: "Hand") -> None:
        """Parses and sets special tournament pot (STP) or bomb pot amounts.

        This function searches the hand text for STP or bomb pot amounts and
        updates the hand object with the corresponding values.

        Args:
            hand (Hand): The Hand object to update with STP or bomb pot information.

        Returns:
            None
        """
        if m := self.re_hutp.search(hand.handText):
            hand.addSTP(m.group("AMOUNT"))
        elif m := self.re_escape_pot.search(hand.handText):
            hand.addSTP(m.group("AMOUNT"))
            # Store bomb pot amount in dedicated field
            hand.bombPot = int(float(m.group("AMOUNT")) * 100)  # Convert to cents

    def readHoleCards(self, hand: "Hand") -> None:
        """Read and parse hole cards for all players from hand history.

        Processes hero cards from PREFLOP/DEAL/BLINDSANTES streets and other players'
        cards from remaining streets. Handles stud games with special logic for THIRD street.

        Args:
            hand: Hand object to add hole cards to
        """
        self._process_hero_streets(hand)
        self._process_other_streets(hand)

    def _process_hero_streets(self, hand: "Hand") -> None:
        """Processes and adds hero hole cards from the initial streets.

        This function iterates through the preflop, deal, and blinds/antes streets
        to extract and assign the hero's hole cards to the hand object.

        Args:
            hand (Hand): The Hand object to update with hero hole cards.

        Returns:
            None
        """
        for street in ("PREFLOP", "DEAL", "BLINDSANTES"):
            if street in hand.streets:
                m = self.re_hero_cards.finditer(hand.streets[street])
                for found in m:
                    if newcards := [c for c in found.group("NEWCARDS").split(" ") if c != "X"]:
                        hand.hero = found.group("PNAME")
                        self._add_hero_hole_cards(hand, street, newcards)

    def _add_hero_hole_cards(self, hand: "Hand", street: str, newcards: list[str]) -> None:
        """Adds the hero's hole cards for a given street to the hand object.

        This function updates the hand with the hero's hole cards, marking them as dealt and not shown or mucked.

        Args:
            hand (Hand): The Hand object to update with hero hole cards.
            street (str): The street name where the cards are dealt.
            newcards (list[str]): The list of new hole cards for the hero.

        Returns:
            None
        """
        log.debug(
            "DEBUG: %s addHoleCards(%s, %s, %s)",
            hand.handid,
            street,
            hand.hero,
            newcards,
        )
        hand.addHoleCards(
            street,
            hand.hero,
            closed=newcards,
            shown=False,
            mucked=False,
            dealt=True,
        )
        log.debug("Hero cards %s: %s", hand.hero, newcards)

    def _process_other_streets(self, hand: "Hand") -> None:
        """Processes and adds player hole cards from streets other than the initial ones.

        This function iterates through all streets except PREFLOP, DEAL, and BLINDSANTES,
        extracting and assigning hole cards for each player found in those streets.

        Args:
            hand (Hand): The Hand object to update with player hole cards.

        Returns:
            None
        """
        for street, text in list(hand.streets.items()):
            if not text or street in ("PREFLOP", "DEAL", "BLINDSANTES"):
                continue  # already done these
            m = self.re_hero_cards.finditer(hand.streets[street])
            for found in m:
                self._process_player_cards(hand, street, found)

    def _process_player_cards(self, hand: "Hand", street: str, found: Match[str]) -> None:
        """Processes and adds a player's hole cards for a given street.

        This function extracts new and old cards for a player from the match object and
        updates the hand object accordingly, handling special logic for stud games on the THIRD street.

        Args:
            hand (Hand): The Hand object to update with player hole cards.
            street (str): The street name where the cards are dealt.
            found: The regex match object containing player and card information.

        Returns:
            None
        """
        player = found.group("PNAME")
        newcards = self._extract_cards(found.group("NEWCARDS"))
        oldcards = self._extract_cards(found.group("OLDCARDS"))

        if street == "THIRD" and len(newcards) == self.STUD_HOLE_CARDS_COUNT:
            self._add_stud_hero_cards(hand, street, player, newcards)
        else:
            self._add_regular_hole_cards(hand, street, player, newcards, oldcards)

    def _extract_cards(self, cards_str: str | None) -> list[str]:
        """Extracts a list of valid card strings from the input.

        This function splits the input string into individual cards, filtering out any placeholder values such as 'X'.
        If the input is None, it returns an empty list.

        Args:
            cards_str (str | None): The string containing card values separated by spaces.

        Returns:
            list[str]: A list of valid card strings.
        """
        if cards_str is None:
            return []
        return [c for c in cards_str.split(" ") if c != "X"]

    def _add_stud_hero_cards(self, hand: "Hand", street: str, player: str, newcards: list[str]) -> None:
        """Adds the hero's hole cards for stud games on the THIRD street.

        This function sets the hero, marks the player as dealt,
        and adds the appropriate closed and open cards for stud games.

        Args:
            hand (Hand): The Hand object to update with hero hole cards.
            street (str): The street name where the cards are dealt.
            player (str): The player's name.
            newcards (list[str]): The list of new hole cards for the hero.

        Returns:
            None
        """
        hand.hero = player
        hand.dealt.add(player)  # need this for stud??
        hand.addHoleCards(
            street,
            player,
            closed=newcards[:2],
            open=[newcards[2]],
            shown=False,
            mucked=False,
            dealt=False,
        )

    def _add_regular_hole_cards(
        self,
        hand: "Hand",
        street: str,
        player: str,
        newcards: list[str],
        oldcards: list[str],
    ) -> None:
        """Adds a player's regular hole cards for a given street to the hand object.

        This function updates the hand with the player's open and closed hole cards for the specified street,
        marking them as not shown, not mucked, and not dealt.

        Args:
            hand (Hand): The Hand object to update with player hole cards.
            street (str): The street name where the cards are dealt.
            player (str): The player's name.
            newcards (list[str]): The list of new open cards for the player.
            oldcards (list[str]): The list of closed cards for the player.

        Returns:
            None
        """
        hand.addHoleCards(
            street,
            player,
            open=newcards,
            closed=oldcards,
            shown=False,
            mucked=False,
            dealt=False,
        )

    def readAction(self, hand: "Hand", street: str) -> None:
        """Parses and processes all player actions for a given street.

        This function iterates through the actions in the specified street, determines the action type and player,
        and delegates processing to the appropriate handler.

        Args:
            hand (Hand): The Hand object to update with action information.
            street (str): The street name to parse actions for.

        Returns:
            None
        """
        streetsplit = hand.streets[street].split("*** SUMMARY ***")
        m = self.re_action.finditer(streetsplit[0])
        for action in m:
            acts = action.groupdict()
            log.debug("read actions: acts: %s", acts)

            action_type = action.group("ATYPE")
            player_name = action.group("PNAME")

            self._process_action(hand, street, action_type, player_name, action)

            log.debug("Processed %s", acts)
            log.debug("committed %s", hand.pot.committed)

    def _process_action(
        self,
        hand: "Hand",
        street: str,
        action_type: str,
        player_name: str,
        action: Match[str],
    ) -> None:
        """Processes a single player action for a given street.

        This function determines the type of action (fold, check, call, raise, bet, discard, or stand pat) and
        updates the hand object accordingly. If the action type is not recognized, it logs an error.

        Args:
            hand (Hand): The Hand object to update with the action.
            street (str): The street name where the action occurs.
            action_type (str): The type of action performed.
            player_name (str): The name of the player performing the action.
            action: The regex match object containing action details.

        Returns:
            None
        """
        if action_type == " folds":
            hand.addFold(street, player_name)
        elif action_type == " checks":
            hand.addCheck(street, player_name)
        elif action_type == " calls":
            hand.addCall(street, player_name, action.group("BET"))
        elif action_type == " raises":
            self._process_raise_action(hand, street, player_name, action)
        elif action_type == " bets":
            self._process_bet_action(hand, street, player_name, action)
        elif action_type == " discards":
            hand.addDiscard(
                street,
                player_name,
                action.group("BET"),
                action.group("DISCARDED"),
            )
        elif action_type == " stands pat":
            hand.addStandsPat(street, player_name)
        else:
            log.error(
                "Unimplemented readAction: '%s' '%s'",
                player_name,
                action_type,
            )

    def _process_raise_action(self, hand: "Hand", street: str, player_name: str, action: Match[str]) -> None:
        """Processes a raise action for a given street and player.

        This function checks for a bring-in amount and adds it to the raise-to amount if present,
        then updates the hand object with the correct raise information.

        Args:
            hand (Hand): The Hand object to update with the raise action.
            street (str): The street name where the raise occurs.
            player_name (str): The name of the player performing the raise.
            action: The regex match object containing raise details.

        Returns:
            None
        """
        if bringin := [act[2] for act in hand.actions[street] if act[0] == player_name and act[1] == "bringin"]:
            betto = str(Decimal(action.group("BETTO")) + bringin[0])
        else:
            betto = action.group("BETTO")
        hand.addRaiseTo(street, player_name, betto)

    def _process_bet_action(self, hand: "Hand", street: str, player_name: str, action: re.Match[str]) -> None:
        """Processes a bet action for a given street and player.

        This function determines whether the bet should be treated as a raise or a standard bet based on the street,
        and updates the hand object accordingly.

        Args:
            hand (Hand): The Hand object to update with the bet action.
            street (str): The street name where the bet occurs.
            player_name (str): The name of the player making the bet.
            action (re.Match[str]): The regex match object containing bet details.

        Returns:
            None
        """
        if street in {"PREFLOP", "DEAL", "THIRD", "BLINDSANTES"}:
            hand.addRaiseBy(street, player_name, action.group("BET"))
        else:
            hand.addBet(street, player_name, action.group("BET"))

    def readShowdownActions(self, hand: "Hand") -> None:
        """Parses and processes all showdown actions in the hand.

        This function extracts shown cards for each player at showdown and updates the hand object accordingly.

        Args:
            hand (Hand): The Hand object to update with showdown actions.

        Returns:
            None
        """
        for shows in self.re_showdown_action.finditer(hand.handText):
            log.debug("add show actions %s", shows)
            cards = shows.group("CARDS")
            cards = cards.split(" ")
            log.debug("add Shown Cards(%s, %s)", cards, shows.group("PNAME"))
            hand.addShownCards(cards, shows.group("PNAME"))

    def readCollectPot(self, hand: "Hand") -> None:
        """Parses and processes all pot collection actions in the hand.

        This function identifies players who collect pots and updates the hand object with the collected amounts.

        Args:
            hand (Hand): The Hand object to update with pot collection actions.

        Returns:
            None
        """
        hand.setUncalledBets(True)
        for m in self.re_collect_pot.finditer(hand.handText):
            hand.addCollectPot(player=m.group("PNAME"), pot=m.group("POT"))

    def readShownCards(self, hand: "Hand") -> None:
        """Parses and processes all shown cards in the hand.

        This function extracts shown cards for each player from the hand text and updates the hand object,
        marking cards as shown and not mucked.

        Args:
            hand (Hand): The Hand object to update with shown card information.

        Returns:
            None
        """
        for m in self.re_shown_cards.finditer(hand.handText):
            log.debug("Read shown cards: %s", m.group(0))
            cards = m.group("CARDS")
            cards = cards.split(
                " ",
            )  # needs to be a list, not a set--stud needs the order
            (shown, mucked) = (False, False)
            if m.group("CARDS") is not None:
                shown = True
                string = m.group("STRING")
                log.debug("%s %s %s %s", m.group("PNAME"), cards, shown, mucked)
                hand.addShownCards(
                    cards=cards,
                    player=m.group("PNAME"),
                    shown=shown,
                    mucked=mucked,
                    string=string,
                )

    def readSummaryInfo(self, summary_info_list: list[str]) -> bool:  # noqa: ARG002
        """Implement the abstract method from HandHistoryConverter."""
        # Add the actual implementation here, or use a placeholder if not needed
        log.info("Reading summary info for Winamax.")
        return True

    def readTourneyResults(self, hand: "Hand") -> None:  # noqa: ARG002
        """Implement the abstract method from HandHistoryConverter."""
        # Add the actual implementation here, or use a placeholder if not needed
        log.info("Reading tournay result info for Winamax.")

    @staticmethod
    def getTableTitleRe(
        _game_type: str | None = None,
        table_name: str | None = None,
        tournament: str | None = None,
        table_number: str | None = None,
    ) -> str:
        """Generate regex pattern for matching Winamax table titles.

        Args:
            game_type: Type of game (unused but kept for compatibility)
            table_name: Name of the table
            tournament: Tournament identifier
            table_number: Table number for tournaments

        Returns:
            Compiled regex pattern string for matching table titles
        """
        log.info(
            "Winamax.getTableTitleRe: table_name='%s' tournament='%s' table_number='%s'",
            table_name,
            tournament,
            table_number,
        )
        sys_platform = platform.system()  # Linux, Windows, Darwin
        # Use word boundaries to prevent partial matches (e.g., "Casablanca" matching "Casablanca 02")
        if sys_platform[:5] == "Linux":
            regex = rf"^Winamax {re.escape(table_name or '')}(\s|$)"
        else:
            regex = rf"^Winamax {re.escape(table_name or '')} /"
        log.debug("regex get table cash title: %s", regex)
        if tournament:
            regex = rf"Winamax\s+([^\(]+)\({tournament}\)\(#0*{table_number}\)"

            log.debug("regex get mtt sng expresso cash title: %s", regex)
        log.info("Winamax.getTableTitleRe: returns: '%s'", regex)
        return regex

    def readOther(self, hand: "Hand") -> None:
        """Read other information from hand that doesn't fit standard categories.

        Args:
            hand: The Hand object to read other information from.

        Returns:
            None

        """
