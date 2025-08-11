"""BetOnline poker hand history parser for FPDB.

Copyright 2008-2011, Chaz Littlejohn

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
"""


import datetime
import re
from decimal import Decimal
from typing import Any, ClassVar

from past.utils import old_div

from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger

# TODO(fpdb): straighten out discards for draw games


log = get_logger("parser")
# BetOnline HH Format


class BetOnline(HandHistoryConverter):
    """BetOnline poker hand history converter."""
    # Class Variables

    sitename = "BetOnline"
    skin = "BetOnline"
    filetype = "text"
    codepage = ("utf8", "cp1252")
    site_id = 19  # Needs to match id entry in Sites database
    sym: ClassVar[dict[str, str]] = {
        "USD": r"\$",
        "CAD": r"\$",
        "T$": "",
        "EUR": "€",
        "GBP": "\xa3",
        "play": "",
    }  # ADD Euro, Sterling, etc HERE
    substitutions: ClassVar[dict[str, str]] = {
        "LS": r"\$|€|",  # legal currency symbols - Euro(cp1252, utf-8)
        "PLYR": r"(?P<PNAME>.+?)",
        "NUM": r".,\d",
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
        "200.00": ("50.00", "100.00"),
        "200": ("50.00", "100.00"),
        "400.00": ("100.00", "200.00"),
        "400": ("100.00", "200.00"),
        "800.00": ("200.00", "400.00"),
        "800": ("200.00", "400.00"),
        "1000.00": ("250.00", "500.00"),
        "1000": ("250.00", "500.00"),
    }

    limits: ClassVar[dict[str, str]] = {"No Limit": "nl", "Pot Limit": "pl", "Limit": "fl", "LIMIT": "fl"}
    games: ClassVar[dict[str, tuple[str, str]]] = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi/Lo": ("hold", "omahahilo"),
        "Razz": ("stud", "razz"),
        "7 Card Stud": ("stud", "studhi"),
        "7 Card Stud Hi/Lo": ("stud", "studhilo"),
        "Badugi": ("draw", "badugi"),
        "Triple Draw 2-7 Lowball": ("draw", "27_3draw"),
        "Single Draw 2-7 Lowball": ("draw", "27_1draw"),
        "5 Card Draw": ("draw", "fivedraw"),
    }
    mixes: ClassVar[dict[str, str]] = {
        "HORSE": "horse",
        "8-Game": "8game",
        "HOSE": "hose",
        "Mixed PLH/PLO": "plh_plo",
        "Mixed Omaha H/L": "plo_lo",
        "Mixed Hold'em": "mholdem",
        "Triple Stud": "3stud",
    }  # Legal mixed games
    currencies: ClassVar[dict[str, str]] = {"€": "EUR", "$": "USD", "": "T$"}

    skins: ClassVar[dict[str, str]] = {
        "BetOnline Poker": "BetOnline",
        "PayNoRake": "PayNoRake",
        "ActionPoker.com": "ActionPoker",
        "Gear Poker": "GearPoker",
        "SportsBetting.ag Poker": "SportsBetting.ag",
        "Tiger Gaming": "Tiger Gaming",
    }  # Legal mixed games

    # Static regexes
    re_game_info: ClassVar[re.Pattern[str]] = re.compile(
        """
          (?P<SKIN>BetOnline\\sPoker|PayNoRake|ActionPoker\\.com|Gear\\sPoker|SportsBetting\\.ag\\sPoker|Tiger\\sGaming)\\sGame\\s\\#(?P<HID>[0-9]+):\\s+
          (\\{{.*\\}}\\s+)?(Tournament\\s\\#                # open paren of tournament info
          (?P<TOURNO>\\d+):\\s?
          # here's how I plan to use LS
          (?P<BUYIN>(?P<BIAMT>({LS})[{NUM}]+)?\\+?(?P<BIRAKE>({LS})[{NUM}]+)?\\+?(?P<BOUNTY>({LS})[{NUM}]+)?\\s?|Freeroll|)\\s+)?
          # close paren of tournament info
          (?P<GAME>Hold\'em|Razz|7\\sCard\\sStud|7\\sCard\\sStud\\sHi/Lo|Omaha|Omaha\\sHi/Lo|Badugi|Triple\\sDraw\\s2\\-7\\sLowball|Single\\sDraw\\s2\\-7\\sLowball|5\\sCard\\sDraw)\\s
          (?P<LIMIT>No\\sLimit|Limit|LIMIT|Pot\\sLimit)?,?\\s?
          (
              \\(?                            # open paren of the stakes
              (?P<CURRENCY>{LS}|)?
              (?P<SB>[{NUM}]+)/({LS})?
              (?P<BB>[{NUM}]+)
              \\)?                        # close paren of the stakes
          )?
          \\s?-\\s
          (?P<DATETIME>.*$)
        """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_player_info: ClassVar[re.Pattern[str]] = re.compile(
        r"""
          ^Seat\s(?P<SEAT>[0-9]+):\s
          (?P<PNAME>.*)\s
          \(({LS})?(?P<CASH>[{NUM}]+)\sin\s[cC]hips\)""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_hand_info1: ClassVar[re.Pattern[str]] = re.compile(
        """
          ^Table\\s\'(?P<TABLE>[\\/,\\.\\-\\ &%\\$\\#a-zA-Z\\d\'\\(\\)]+)\'\\s
          ((?P<MAX>\\d+)-max\\s)?
          (?P<MONEY>\\((Play\\sMoney|Real\\sMoney)\\)\\s)?
          (Seat\\s\\#(?P<BUTTON>\\d+)\\sis\\sthe\\sbutton)?""",
        re.MULTILINE | re.VERBOSE,
    )

    re_hand_info2: ClassVar[re.Pattern[str]] = re.compile(
        """
          ^Table\\s(?P<TABLE>[\\/,\\.\\-\\ &%\\$\\#a-zA-Z\\d\']+)\\s
          (?P<MONEY>\\((Play\\sMoney|Real\\sMoney)\\)\\s)?
          (Seat\\s\\#(?P<BUTTON>\\d+)\\sis\\sthe\\sbutton)?""",
        re.MULTILINE | re.VERBOSE,
    )

    re_identify: ClassVar[re.Pattern[str]] = re.compile(
        r"(BetOnline\sPoker|PayNoRake|ActionPoker\.com|Gear\sPoker|SportsBetting\.ag\sPoker|Tiger\sGaming)\sGame\s\#\d+",
    )
    re_split_hands: ClassVar[re.Pattern[str]] = re.compile("\n\n\n+")
    re_tail_split_hands: ClassVar[re.Pattern[str]] = re.compile("(\n\n\n+)")
    re_button: ClassVar[re.Pattern[str]] = re.compile(r"Seat #(?P<BUTTON>\d+) is the button", re.MULTILINE)
    re_board1: ClassVar[re.Pattern[str]] = re.compile(
        r"Board \[(?P<FLOP>\S\S\S? \S\S\S? \S\S\S?)?\s?(?P<TURN>\S\S\S?)?\s?(?P<RIVER>\S\S\S?)?\]",
    )
    re_board2: ClassVar[re.Pattern[str]] = re.compile(r"\[(?P<CARDS>.+)\]")
    re_hole: ClassVar[re.Pattern[str]] = re.compile(r"\*\*\*\sHOLE\sCARDS\s\*\*\*")

    re_date_time1: ClassVar[re.Pattern[str]] = re.compile(
        r"""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+"""
        r"""(?P<H>[0-9]+):(?P<MIN>[0-9]+)(:(?P<S>[0-9]+))?\s(?P<TZ>.*$)""",
        re.MULTILINE,
    )
    re_date_time2: ClassVar[re.Pattern[str]] = re.compile(
        r"""(?P<Y>[0-9]{4})\-(?P<M>[0-9]{2})\-(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""",
        re.MULTILINE,
    )

    re_post_sb: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR}: [Pp]osts small blind ({LS})?(?P<SB>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_post_bb: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR}: ([Pp]osts big blind|[Pp]osts? [Nn]ow)( ({LS})?(?P<BB>[{NUM}]+))?".format(**substitutions),
        re.MULTILINE,
    )
    re_antes: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR}: ante processed ({LS})?(?P<ANTE>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_bring_in: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR}: brings[- ]in( low|) for ({LS})?(?P<BRINGIN>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_post_both: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR}: [Pp]ost dead ({LS})?(?P<SBBB>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_hero_cards: ClassVar[re.Pattern[str]] = re.compile(
        r"^Dealt [Tt]o {PLYR}(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(**substitutions),
        re.MULTILINE,
    )
    re_action: ClassVar[re.Pattern[str]] = re.compile(
        r"""
                        ^{PLYR}:?(?P<ATYPE>\shas\sleft\sthe\stable|\s[Bb]ets|\s[Cc]hecks|\s[Rr]aises|\s[Cc]alls|\s[Ff]olds|\s[Dd]iscards|\s[Ss]tands\spat|\sReraises)
                        (\s({LS})?(?P<BET>[{NUM}]+))?(\sto\s({LS})?(?P<BETTO>[{NUM}]+))?  # number discarded in <BET>
                        \s*(and\sis\s[Aa]ll.[Ii]n)?
                        (\son|\scards?)?
                        (\s\[(?P<CARDS>.+?)\])?\.?\s*$""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    re_showdown_action: ClassVar[re.Pattern[str]] = re.compile(
        r"^{}: shows (?P<CARDS>.*)".format(substitutions["PLYR"]), re.MULTILINE,
    )
    re_sits_out: ClassVar[re.Pattern[str]] = re.compile("^{} sits out".format(substitutions["PLYR"]), re.MULTILINE)
    re_joins_table: ClassVar[re.Pattern[str]] = re.compile(r"^.+ joins the table at seat #\d+", re.MULTILINE)
    re_total_pot: ClassVar[re.Pattern[str]] = re.compile(
        r"^Total pot (?P<POT>[%(NUM)s]+)( \| Rake (?P<RAKE>[%(NUM)s]+))?", re.MULTILINE,
    )
    re_shown_cards: ClassVar[re.Pattern[str]] = re.compile(
        r"Seat (?P<SEAT>[0-9]+): {PLYR} (\(.+?\)  )?(?P<SHOWED>showed|mucked) "
        r"\[(?P<CARDS>.*)\]( and won \([{NUM}]+\))?".format(**substitutions),
        re.MULTILINE,
    )
    re_collect_pot: ClassVar[re.Pattern[str]] = re.compile(
        r"Seat (?P<SEAT>[0-9]+): {PLYR} (\(.+?\)  )?(collected|showed \[.*\] and won) "
        r"\(({LS})?(?P<POT>[{NUM}]+)\)".format(**substitutions),
        re.MULTILINE,
    )

    def compilePlayerRegexs(self, hand: Any) -> None:
        """Compile player-specific regex patterns (not implemented)."""

    def readSupportedGames(self) -> list[list[str]]:
        """Return list of supported game types."""
        return [
            ["ring", "hold", "nl"],
            ["ring", "hold", "pl"],
            ["ring", "hold", "fl"],
            ["tour", "hold", "nl"],
            ["tour", "hold", "pl"],
            ["tour", "hold", "fl"],
        ]

    def determineGameType(self, hand_text: str) -> dict[str, Any]:
        """Determine the game type from hand text."""
        m = self._validate_game_info(hand_text)
        mg = m.groupdict()

        info = self._parse_basic_game_info(mg, hand_text)
        self._set_game_type(info, mg)
        self._process_fixed_limit_blinds(info, mg, hand_text)

        return info

    def _validate_game_info(self, hand_text: str) -> re.Match[str]:
        """Validate and extract game info from hand text."""
        m = self.re_game_info.search(hand_text)
        if not m:
            self._handle_missing_game_info(hand_text)
        return m

    def _handle_missing_game_info(self, hand_text: str) -> None:
        """Handle cases where game info is not found."""
        # BetOnline starts writing the hh the moment you sit down.
        # Test if the hh contains the join line, and throw a partial if so.
        m2 = self.re_joins_table.search(hand_text)
        if not m2:
            tmp = hand_text[0:200]
            log.error("determineGameType not found: '%s'", tmp)
            raise FpdbParseError
        msg = "BetOnlineToFpdb.determineGameType: Partial hand history: 'Player joining table'"
        raise FpdbHandPartial(msg)

    def _parse_basic_game_info(self, mg: dict[str, Any], hand_text: str) -> dict[str, Any]:
        """Parse basic game information from match groups."""
        info: dict[str, Any] = {}

        # Set limit type
        info["limitType"] = self.limits.get(mg["LIMIT"], self.limits["No Limit"])

        # Handle Omaha detection for PL games
        if info["limitType"] == "pl":
            self._detect_omaha_game(info, hand_text)

        # Set skin
        if "SKIN" in mg:
            self.skin = self.skins[mg["SKIN"]]

        # Set base game and category
        if "GAME" in mg and not info.get("base"):
            (info["base"], info["category"]) = self.games[mg["GAME"]]

        # Set blinds
        if "SB" in mg:
            info["sb"] = self.clearMoneyString(mg["SB"])
        if "BB" in mg:
            info["bb"] = self.clearMoneyString(mg["BB"])

        # Set currency
        info["currency"] = self.currencies.get(mg.get("CURRENCY"), "USD")

        # Set mix
        if "MIXED" in mg and mg["MIXED"] is not None:
            info["mix"] = self.mixes[mg["MIXED"]]

        return info

    def _detect_omaha_game(self, info: dict[str, Any], hand_text: str) -> None:
        """Detect if PL game is Omaha based on card count."""
        m = self.re_hero_cards.search(hand_text)
        omaha_card_count = 4
        if m and len(m.group("NEWCARDS").split(" ")) == omaha_card_count:
            (info["base"], info["category"]) = self.games["Omaha"]

    def _set_game_type(self, info: dict[str, Any], mg: dict[str, Any]) -> None:
        """Set game type (ring vs tour)."""
        info["type"] = "ring" if "TOURNO" in mg and mg["TOURNO"] is None else "tour"

    def _process_fixed_limit_blinds(self, info: dict[str, Any], mg: dict[str, Any], hand_text: str) -> None:
        """Process fixed limit blinds."""
        if info["limitType"] != "fl" or info.get("bb") is None:
            return

        if info["type"] == "ring":
            self._set_ring_game_blinds(info, mg, hand_text)
        else:
            self._set_tournament_blinds(info)

    def _set_ring_game_blinds(self, info: dict[str, Any], mg: dict[str, Any], hand_text: str) -> None:
        """Set blinds for ring games."""
        try:
            info["sb"] = self.Lim_Blinds[info["BB"]][0]
            info["bb"] = self.Lim_Blinds[info["BB"]][1]
        except KeyError:
            tmp = hand_text[0:200]
            log.exception("Lim_Blinds has no lookup for '%s' - '%s'", mg["BB"], tmp)
            raise FpdbParseError from None

    def _set_tournament_blinds(self, info: dict[str, Any]) -> None:
        """Set blinds for tournament games."""
        info["sb"] = str(
            (old_div(Decimal(info["SB"]), 2)).quantize(Decimal("0.01")),
        )
        info["bb"] = str(Decimal(info["SB"]).quantize(Decimal("0.01")))

    def readHandInfo(self, hand: Any) -> None:
        """Read basic hand information from hand text."""
        info = self._extract_hand_info(hand.handText)
        self._process_hand_info(hand, info)
        self._validate_hand_completeness(hand)

    def _extract_hand_info(self, hand_text: str) -> dict[str, Any]:
        """Extract hand information from hand text."""
        if self.skin in ("ActionPoker", "GearPoker"):
            m = self.re_hand_info2.search(hand_text, re.DOTALL)
        else:
            m = self.re_hand_info1.search(hand_text, re.DOTALL)
        m2 = self.re_game_info.search(hand_text)

        if m is None or m2 is None:
            tmp = hand_text[0:200]
            log.error("readHandInfo not found: '%s'", tmp)
            raise FpdbParseError

        info: dict[str, Any] = {}
        info.update(m.groupdict())
        info.update(m2.groupdict())
        return info

    def _process_hand_info(self, hand: Any, info: dict[str, Any]) -> None:
        """Process extracted hand information."""
        # Process datetime
        if "DATETIME" in info:
            self._process_datetime(hand, info["DATETIME"])

        # Process basic hand info
        self._process_basic_hand_attributes(hand, info)

        # Process tournament info
        if "TOURNO" in info:
            hand.tourNo = info["TOURNO"]
            if "BUYIN" in info and hand.tourNo is not None:
                self._process_buyin_info(hand, info)

        # Process table info
        self._process_table_attributes(hand, info)

    def _process_basic_hand_attributes(self, hand: Any, info: dict[str, Any]) -> None:
        """Process basic hand attributes."""
        if "HID" in info:
            hand.handid = info["HID"]
        if "MONEY" in info and info["MONEY"] == "(Play Money) ":
            hand.gametype["currency"] = "play"
        if "LEVEL" in info:
            hand.level = info["LEVEL"]

    def _process_table_attributes(self, hand: Any, info: dict[str, Any]) -> None:
        """Process table-related attributes."""
        if "TABLE" in info:
            self._process_table_info(hand, info["TABLE"])
        if "BUTTON" in info:
            hand.buttonpos = info["BUTTON"]
        if "MAX" in info and info["MAX"] is not None:
            hand.maxseats = int(info["MAX"])

    def _process_buyin_info(self, hand: Any, info: dict[str, Any]) -> None:
        """Process tournament buy-in information."""
        if not info["BUYIN"] or info["BUYIN"] == "Freeroll":
            hand.buyin = 0
            hand.fee = 0
            hand.buyinCurrency = "FREE"
        else:
            self._detect_buyin_currency(hand, info)
            self._process_buyin_amounts(hand, info)

    def _detect_buyin_currency(self, hand: Any, info: dict[str, Any]) -> None:
        """Detect buy-in currency from buyin string."""
        buyin_str = info["BUYIN"]
        if "$" in buyin_str:
            hand.buyinCurrency = "USD"
        elif "€" in buyin_str:
            hand.buyinCurrency = "EUR"
        elif re.match("^[0-9+]*$", buyin_str):
            hand.buyinCurrency = "play"
        else:
            # TODO(fpdb): handle other currencies, play money
            msg = f"BetOnlineToFpdb.readHandInfo: Failed to detect currency. Hand ID: {hand.handid}: '{buyin_str}'"
            raise FpdbParseError(msg)

    def _process_buyin_amounts(self, hand: Any, info: dict[str, Any]) -> None:
        """Process buy-in amounts and fees."""
        info["BIAMT"] = info["BIAMT"].strip("$€")

        if info["BOUNTY"] is not None:
            # There is a bounty, switch BOUNTY and BIRAKE values
            info["BOUNTY"], info["BIRAKE"] = info["BIRAKE"], info["BOUNTY"]
            info["BOUNTY"] = info["BOUNTY"].strip("$€")
            hand.koBounty = int(100 * Decimal(info["BOUNTY"]))
            hand.isKO = True
        else:
            hand.isKO = False

        info["BIRAKE"] = info["BIRAKE"].strip("$€")
        hand.buyin = int(100 * Decimal(info["BIAMT"]))
        hand.fee = int(100 * Decimal(info["BIRAKE"]))

    def _process_table_info(self, hand: Any, table_info: str) -> None:
        """Process table information."""
        if hand.tourNo is not None:
            hand.tablename = re.split("-", table_info)[1]
        else:
            hand.tablename = table_info

    def _process_datetime(self, hand: Any, datetime_str: str) -> None:
        """Process datetime information."""
        # Default values
        datetimestr = "2000/01/01 00:00:00"
        time_zone = "ET"

        if self.skin not in ("ActionPoker", "GearPoker"):
            datetimestr, time_zone = self._parse_datetime_format1(datetime_str)
        else:
            datetimestr = self._parse_datetime_format2(datetime_str)
            time_zone = "ET"

        hand.startTime = datetime.datetime.strptime(
            datetimestr, "%Y/%m/%d %H:%M:%S",
        ).replace(tzinfo=datetime.timezone.utc)
        hand.startTime = HandHistoryConverter.changeTimezone(hand.startTime, time_zone, "UTC")

    def _parse_datetime_format1(self, datetime_str: str) -> tuple[str, str]:
        """Parse datetime format 1."""
        datetimestr = "2000/01/01 00:00:00"
        time_zone = "ET"

        for a in self.re_date_time1.finditer(datetime_str):
            seconds = a.group("S") if a.group("S") else "00"
            datetimestr = "{}/{}/{} {}:{}:{}".format(
                a.group("Y"), a.group("M"), a.group("D"),
                a.group("H"), a.group("MIN"), seconds,
            )
            tz = a.group("TZ")
            if tz == "GMT Standard Time":
                time_zone = "GMT"
            elif tz in ("Pacific Daylight Time", "Pacific Standard Time"):
                time_zone = "PT"
            else:
                time_zone = "ET"

        return datetimestr, time_zone

    def _parse_datetime_format2(self, datetime_str: str) -> str:
        """Parse datetime format 2."""
        datetimestr = "2000/01/01 00:00:00"

        for a in self.re_date_time2.finditer(datetime_str):
            datetimestr = "{}/{}/{} {}:{}:{}".format(
                a.group("Y"), a.group("M"), a.group("D"),
                a.group("H"), a.group("MIN"), a.group("S"),
            )

        return datetimestr

    def _validate_hand_completeness(self, hand: Any) -> None:
        """Validate hand completeness."""
        if not self.re_board1.search(hand.handText) and self.skin not in ("ActionPoker", "GearPoker"):
            msg = f"readHandInfo: Partial hand history: '{hand.handid}'"
            raise FpdbHandPartial(msg)

    def readButton(self, hand: Any) -> None:
        """Read button position from hand text."""
        m = self.re_button.search(hand.handText)
        if m:
            hand.buttonpos = int(m.group("BUTTON"))
        else:
            log.info("readButton: not found")

    def readPlayerStacks(self, hand: Any) -> None:
        """Read player stacks from hand text."""
        m = self.re_player_info.finditer(hand.handText)
        for a in m:
            pname = self.unknownPlayer(hand, a.group("PNAME"))
            hand.addPlayer(
                int(a.group("SEAT")), pname, self.clearMoneyString(a.group("CASH")),
            )

    def markStreets(self, hand: Any) -> None:
        """Mark the different streets in the hand text."""
        self._process_draw_games(hand)

        if hand.gametype["base"] == "hold":
            m = self._mark_hold_streets(hand)
        elif hand.gametype["base"] == "stud":
            m = self._mark_stud_streets(hand)
        elif hand.gametype["base"] == "draw":
            m = self._mark_draw_streets(hand)

        hand.addStreets(m)

    def _process_draw_games(self, hand: Any) -> None:
        """Process draw games by adding DRAW marker."""
        if hand.gametype["category"] not in ("27_1draw", "fivedraw"):
            return

        # isolate the first discard/stand pat line (thanks Carl for the regex)
        discard_split = re.split(
            r"(?:(.+(?: stands pat|: discards).+))", hand.handText, flags=re.DOTALL,
        )
        if len(hand.handText) != len(discard_split[0]):
            # DRAW street found, reassemble, with DRAW marker added
            discard_split[0] += "*** DRAW ***\r\n"
            hand.handText = "".join(discard_split)

    def _mark_hold_streets(self, hand: Any) -> re.Match[str]:
        """Mark streets for hold'em games."""
        m = re.search(
            r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>.+(?=\*\*\* FLOP \*\*\*)|.+)"
            r"(\*\*\* FLOP \*\*\*(?P<FLOP> \[\S\S\S? \S\S\S? \S\S\S?\].+(?=\*\*\* TURN \*\*\*)|.+))?"
            r"(\*\*\* TURN \*\*\* \[\S\S\S? \S\S\S? \S\S\S?\](?P<TURN>\[\S\S\S?\].+(?=\*\*\* RIVER \*\*\*)|.+))?"
            r"(\*\*\* RIVER \*\*\* \[\S\S\S? \S\S\S? \S\S\S? \S\S\S?\](?P<RIVER>\[\S\S\S?\].+))?",
            hand.handText, re.DOTALL,
        )

        # Handle special board cases
        m2 = self.re_board1.search(hand.handText)
        if m and m2:
            m = self._handle_board_variations(hand, m, m2)

        return m

    def _handle_board_variations(self, hand: Any, m: re.Match[str], m2: re.Match[str]) -> re.Match[str]:
        """Handle board variations in hold'em games."""
        if m2.group("FLOP") and not m.group("FLOP"):
            return self._search_flop_board(hand)
        if m2.group("TURN") and not m.group("TURN"):
            return self._search_turn_board(hand)
        if m2.group("RIVER") and not m.group("RIVER"):
            return self._search_river_board(hand)
        return m

    def _search_flop_board(self, hand: Any) -> re.Match[str]:
        """Search for flop board pattern."""
        return re.search(
            r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>.+(?=Board )|.+)"
            r"(Board \[(?P<FLOP>\S\S\S? \S\S\S? \S\S\S?)?\s?(?P<TURN>\S\S\S?)?\s?(?P<RIVER>\S\S\S?)?\])?",
            hand.handText, re.DOTALL,
        )

    def _search_turn_board(self, hand: Any) -> re.Match[str]:
        """Search for turn board pattern."""
        return re.search(
            r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>.+(?=\*\*\* FLOP \*\*\*)|.+)"
            r"(\*\*\* FLOP \*\*\*(?P<FLOP> \[\S\S\S? \S\S\S? \S\S\S?\].+(?=Board )|.+))?"
            r"(Board \[(?P<BFLOP>\S\S\S? \S\S\S? \S\S\S?)?\s?(?P<TURN>\S\S\S?)?\s?(?P<RIVER>\S\S\S?)?\])?",
            hand.handText, re.DOTALL,
        )

    def _search_river_board(self, hand: Any) -> re.Match[str]:
        """Search for river board pattern."""
        return re.search(
            r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>.+(?=\*\*\* FLOP \*\*\*)|.+)"
            r"(\*\*\* FLOP \*\*\*(?P<FLOP> \[\S\S\S? \S\S\S? \S\S\S?\].+(?=\*\*\* TURN \*\*\*)|.+))?"
            r"(\*\*\* TURN \*\*\* \[\S\S\S? \S\S\S? \S\S\S?\](?P<TURN>\[\S\S\S?\].+(?=Board )|.+))?"
            r"(Board \[(?P<BFLOP>\S\S\S? \S\S\S? \S\S\S?)?\s?(?P<BTURN>\S\S\S?)?\s?(?P<RIVER>\S\S\S?)?\])?",
            hand.handText, re.DOTALL,
        )

    def _mark_stud_streets(self, hand: Any) -> re.Match[str]:
        """Mark streets for stud games."""
        return re.search(
            r"(?P<ANTES>.+(?=\*\*\* 3rd STREET \*\*\*)|.+)"
            r"(\*\*\* 3rd STREET \*\*\*(?P<THIRD>.+(?=\*\*\* 4th STREET \*\*\*)|.+))?"
            r"(\*\*\* 4th STREET \*\*\*(?P<FOURTH>.+(?=\*\*\* 5th STREET \*\*\*)|.+))?"
            r"(\*\*\* 5th STREET \*\*\*(?P<FIFTH>.+(?=\*\*\* 6th STREET \*\*\*)|.+))?"
            r"(\*\*\* 6th STREET \*\*\*(?P<SIXTH>.+(?=\*\*\* RIVER \*\*\*)|.+))?"
            r"(\*\*\* RIVER \*\*\*(?P<SEVENTH>.+))?",
            hand.handText, re.DOTALL,
        )

    def _mark_draw_streets(self, hand: Any) -> re.Match[str]:
        """Mark streets for draw games."""
        if hand.gametype["category"] in ("27_1draw", "fivedraw"):
            return re.search(
                r"(?P<PREDEAL>.+(?=\*\*\* DEALING HANDS \*\*\*)|.+)"
                r"(\*\*\* DEALING HANDS \*\*\*(?P<DEAL>.+(?=\*\*\* DRAW \*\*\*)|.+))?"
                r"(\*\*\* DRAW \*\*\*(?P<DRAWONE>.+))?",
                hand.handText, re.DOTALL,
            )
        return re.search(
            r"(?P<PREDEAL>.+(?=\*\*\* DEALING HANDS \*\*\*)|.+)"
            r"(\*\*\* DEALING HANDS \*\*\*(?P<DEAL>.+(?=\*\*\* FIRST DRAW \*\*\*)|.+))?"
            r"(\*\*\* FIRST DRAW \*\*\*(?P<DRAWONE>.+(?=\*\*\* SECOND DRAW \*\*\*)|.+))?"
            r"(\*\*\* SECOND DRAW \*\*\*(?P<DRAWTWO>.+(?=\*\*\* THIRD DRAW \*\*\*)|.+))?"
            r"(\*\*\* THIRD DRAW \*\*\*(?P<DRAWTHREE>.+))?",
            hand.handText, re.DOTALL,
        )


    def readCommunityCards(
        self, hand: Any, street: str,
    ) -> None:
        """Read community cards for a given street."""  # street has been matched by markStreets, so exists in this hand
        if street in (
            "FLOP",
            "TURN",
            "RIVER",
        ):  # a list of streets which get dealt community cards (i.e. all but PREFLOP)
            if self.skin not in ("ActionPoker", "GearPoker"):
                m = self.re_board1.search(hand.handText)
                if m and m.group(street):
                    cards = m.group(street).split(" ")
                    cards = [c.replace("10", "T") for c in cards]
                    hand.setCommunityCards(street, cards)
            else:
                m = self.re_board2.search(hand.streets[street])
                cards = m.group("CARDS").split(" ")
                cards = [c[:-1].replace("10", "T") + c[-1].lower() for c in cards]
                hand.setCommunityCards(street, cards)

    def readAntes(self, hand: Any) -> None:
        """Read ante information from hand text."""
        m = self.re_antes.finditer(hand.handText)
        for player in m:
            if player.group("ANTE") != "0.00":
                pname = self.unknownPlayer(hand, player.group("PNAME"))
                hand.addAnte(pname, self.clearMoneyString(player.group("ANTE")))

    def readBringIn(self, hand: Any) -> None:
        """Read bring-in information from hand text."""
        m = self.re_bring_in.search(hand.handText, re.DOTALL)
        if m:
            hand.addBringIn(m.group("PNAME"), self.clearMoneyString(m.group("BRINGIN")))

    def readBlinds(self, hand: Any) -> None:
        """Read blind information from hand text."""
        live_blind = True
        for a in self.re_post_sb.finditer(hand.handText):
            pname = self.unknownPlayer(hand, a.group("PNAME"))
            sb = self.clearMoneyString(a.group("SB"))
            if live_blind:
                hand.addBlind(pname, "small blind", sb)
                live_blind = False
            else:
                # Post dead blinds as ante
                hand.addBlind(pname, "secondsb", sb)
            if not hand.gametype["sb"] and self.skin in ("ActionPoker", "GearPoker"):
                hand.gametype["sb"] = sb
        for a in self.re_post_bb.finditer(hand.handText):
            pname = self.unknownPlayer(hand, a.group("PNAME"))
            if a.group("BB") is not None:
                bb = self.clearMoneyString(a.group("BB"))
            elif hand.gametype["bb"]:
                bb = hand.gametype["bb"]
            else:
                msg = "BetOnlineToFpdb.readBlinds: Partial hand history: 'No blind info'"
                raise FpdbHandPartial(msg)
            hand.addBlind(pname, "big blind", bb)
            if not hand.gametype["bb"] and self.skin in ("ActionPoker", "GearPoker"):
                hand.gametype["bb"] = bb
        for a in self.re_post_both.finditer(hand.handText):
            if a.group("SBBB") != "0.00":
                pname = self.unknownPlayer(hand, a.group("PNAME"))
                sbbb = self.clearMoneyString(a.group("SBBB"))
                amount = str(Decimal(sbbb) + old_div(Decimal(sbbb), 2))
                hand.addBlind(pname, "both", amount)
            else:
                pname = self.unknownPlayer(hand, a.group("PNAME"))
                hand.addBlind(pname, "secondsb", hand.gametype["sb"])
        self.fixBlinds(hand)

    def fixBlinds(self, hand: Any) -> None:
        """Fix blind information for specific skins."""
        # TODO(fpdb): The following should only trigger when a small blind is missing
        # in ActionPoker hands, or the sb/bb is ALL_IN
        if self.skin in ("ActionPoker", "GearPoker"):
            if hand.gametype["sb"] is None and hand.gametype["bb"] is not None:
                bb_doubled = str(Decimal(hand.gametype["bb"]) * 2)
                if self.Lim_Blinds.get(bb_doubled) is not None:
                    hand.gametype["sb"] = self.Lim_Blinds.get(bb_doubled)[0]
            elif hand.gametype["bb"] is None and hand.gametype["sb"] is not None:
                for _k, v in list(self.Lim_Blinds.items()):
                    if hand.gametype["sb"] == v[0]:
                        hand.gametype["bb"] = v[1]
            if hand.gametype["sb"] is None or hand.gametype["bb"] is None:
                log.error("Failed to fix blinds Hand ID: %s", hand.handid)
                raise FpdbParseError
            hand.sb = hand.gametype["sb"]
            hand.bb = hand.gametype["bb"]

    def unknownPlayer(self, hand: Any, pname: str) -> str:
        """Handle unknown player names."""
        if pname == "Unknown player" or not pname:
            if not pname:
                pname = "Dead"
            if pname not in (p[1] for p in hand.players):
                hand.addPlayer(-1, pname, "0")
        return pname

    def readHoleCards(self, hand: Any) -> None:
        """Read hole cards from hand text."""
        #    streets PREFLOP, PREDRAW, and THIRD are special cases beacause
        #    we need to grab hero's cards
        for street in ("PREFLOP", "DEAL"):
            if street in list(hand.streets.keys()):
                m = self.re_hero_cards.finditer(hand.streets[street])
                for found in m:
                    hand.hero = found.group("PNAME")
                    newcards = found.group("NEWCARDS").split(" ")
                    newcards = [
                        c[:-1].replace("10", "T") + c[-1].lower() for c in newcards
                    ]
                    hand.addHoleCards(
                        street,
                        hand.hero,
                        closed=newcards,
                        shown=False,
                        mucked=False,
                        dealt=True,
                    )

        for street, text in list(hand.streets.items()):
            if not text or street in ("PREFLOP", "DEAL"):
                continue  # already done these
            m = self.re_hero_cards.finditer(hand.streets[street])
            for found in m:
                player = found.group("PNAME")
                if found.group("NEWCARDS") is None:
                    newcards = []
                else:
                    newcards = found.group("NEWCARDS").split(" ")
                    newcards = [
                        c[:-1].replace("10", "T") + c[-1].lower() for c in newcards
                    ]
                if found.group("OLDCARDS") is None:
                    oldcards = []
                else:
                    oldcards = found.group("OLDCARDS").split(" ")
                    oldcards = [
                        c[:-1].replace("10", "T") + c[-1].lower() for c in oldcards
                    ]
                stud_third_cards = 3
                if street == "THIRD" and len(newcards) == stud_third_cards:  # hero in stud game
                    hand.hero = player
                    hand.dealt.add(player)  # need this for stud??
                    hand.addHoleCards(
                        street,
                        player,
                        closed=newcards[0:2],
                        open=[newcards[2]],
                        shown=False,
                        mucked=False,
                        dealt=False,
                    )
                else:
                    hand.addHoleCards(
                        street,
                        player,
                        open=newcards,
                        closed=oldcards,
                        shown=False,
                        mucked=False,
                        dealt=False,
                    )

    def readAction(self, hand: Any, street: str) -> None:
        """Read player actions for a given street."""
        if street == "PREFLOP":
            self._process_preflop_actions(hand, street)

        self._process_street_actions(hand, street)

    def _process_preflop_actions(self, hand: Any, street: str) -> None:
        """Process preflop actions before hole cards."""
        m0 = self.re_action.finditer(self.re_hole.split(hand.handText)[0])
        for action in m0:
            pname = self.unknownPlayer(hand, action.group("PNAME"))
            if action.group("ATYPE") == " has left the table" and pname in (p[1] for p in hand.players):
                hand.addFold(street, pname)

    def _process_street_actions(self, hand: Any, street: str) -> None:
        """Process actions for a given street."""
        m = self.re_action.finditer(hand.streets[street])
        for action in m:
            pname = self.unknownPlayer(hand, action.group("PNAME"))
            atype = action.group("ATYPE")

            if atype in (" folds", " Folds", " has left the table"):
                self._handle_fold_action(hand, street, pname)
            elif atype in (" checks", " Checks"):
                hand.addCheck(street, pname)
            elif atype in (" calls", " Calls"):
                hand.addCall(street, pname, self.clearMoneyString(action.group("BET")))
            elif atype in (" raises", " Raises", " Reraises"):
                hand.addCallandRaise(
                    street, pname, self.clearMoneyString(action.group("BET")),
                )
            elif atype in (" bets", " Bets"):
                hand.addBet(street, pname, self.clearMoneyString(action.group("BET")))
            elif atype == " discards":
                hand.addDiscard(
                    street, pname, action.group("BET"), action.group("CARDS"),
                )
            elif atype == " stands pat":
                hand.addStandsPat(street, pname, action.group("CARDS"))
            else:
                log.debug(
                    "Unimplemented readAction: '%s' '%s'", action.group("PNAME"), atype,
                )

    def _handle_fold_action(self, hand: Any, street: str, pname: str) -> None:
        """Handle fold action if player is in the hand."""
        if pname in (p[1] for p in hand.players):
            hand.addFold(street, pname)

    def readShowdownActions(self, hand: Any) -> None:
        """Read showdown actions from hand text."""
        # TODO(fpdb): pick up mucks also??
        for shows in self.re_showdown_action.finditer(hand.handText):
            cards = shows.group("CARDS").split(" ")
            cards = [c[:-1].replace("10", "T") + c[-1].lower() for c in cards]
            hand.addShownCards(cards, shows.group("PNAME"))

    def readCollectPot(self, hand: Any) -> None:
        """Read pot collection information from hand text."""
        hand.adjustCollected = True
        for m in self.re_collect_pot.finditer(hand.handText):
            hand.addCollectPot(player=m.group("PNAME"), pot=m.group("POT"))
        for m in self.re_total_pot.finditer(hand.handText):
            if hand.rakes.get("pot"):
                hand.rakes["pot"] += Decimal(self.clearMoneyString(m.group("POT")))
            else:
                hand.rakes["pot"] = Decimal(self.clearMoneyString(m.group("POT")))

    def readSummaryInfo(self, summary_info_list: list[Any]) -> bool:  # noqa: ARG002
        """Read summary information (not implemented)."""
        log.info("enter method readSummaryInfo.")
        log.debug("Method readSummaryInfo non implemented.")
        return True

    def readShownCards(self, hand: Any) -> None:
        """Read shown cards from hand text."""
        for m in self.re_shown_cards.finditer(hand.handText):
            if m.group("CARDS") is not None:
                pname = self.unknownPlayer(hand, m.group("PNAME"))
                cards = m.group("CARDS")
                cards = cards.split(
                    " ",
                )  # needs to be a list, not a set--stud needs the order
                cards = [
                    c[:-1].replace("10", "T") + c[-1].lower()
                    for c in cards
                    if len(c) > 0
                ]
                (shown, mucked) = (False, False)
                if m.group("SHOWED") == "showed":
                    shown = True
                elif m.group("SHOWED") == "mucked":
                    mucked = True
                holdem_hand_size = 2
                if hand.gametype["category"] == "holdem" and len(cards) > holdem_hand_size:
                    continue
                # print "DEBUG: hand.addShownCards(%s, %s, %s, %s)" %(cards, m.group('PNAME'), shown, mucked)
                hand.addShownCards(
                    cards=cards, player=pname, shown=shown, mucked=mucked, string=None,
                )

    @staticmethod
    def getTableTitleRe(
        type_: str,
        table_name: str | None = None,
        tournament: str | None = None,
        table_number: str | None = None,
    ) -> str:
        """Returns string to search in windows titles."""
        if type_ == "tour":
            return (
                r"\("
                + re.escape(str(tournament))
                + r"\-"
                + re.escape(str(table_number))
                + r"\)"
            )
        return re.escape(table_name)
