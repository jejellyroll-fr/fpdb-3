"""Bovada poker hand history parser for FPDB.

Copyright 2008-2012, Chaz Littlejohn

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

# TODO(fpdb): straighten out discards for draw games

import datetime
import re
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger

if TYPE_CHECKING:
    from Hand import Hand

# Bovada HH Format
log = get_logger("bovada_parser")


class Bovada(HandHistoryConverter):
    """Bovada poker hand history converter."""

    # Class Variables

    sitename = "Bovada"
    filetype = "text"
    codepage = ("utf8", "cp1252")
    site_id = 21  # Needs to match id entry in Sites database
    summary_in_file = True
    copy_game_header = True
    sym: ClassVar[dict[str, str]] = {"USD": r"\$", "T$": "", "play": ""}  # ADD Euro, Sterling, etc HERE
    substitutions: ClassVar[dict[str, str]] = {
        "LEGAL_ISO": "USD",  # legal ISO currency codes
        "LS": r"\$|",  # legal currency symbols - Euro(cp1252, utf-8)
        "PLYR": r"(?P<PNAME>.+?)",
        "CUR": r"(\$|)",
        "NUM": r".,\d",
    }

    # Action type constants
    ACTION_FOLD = " Fold"
    ACTION_CHECK = " Checks"
    ACTION_CALL = " Calls"
    ACTION_CALL_ALT = " Call"
    ACTION_RAISES = (" Raises", " raises", " All-in(raise)", " All-in(raise-timeout)")
    ACTION_BETS = (" Bets", " bets", " Double bets")
    ACTION_ALLIN = " All-in"
    ACTION_BRING_IN = " Bring_in chip"
    ACTION_IGNORED = (" Card dealt to a spot", " Big blind/Bring in")
    ACTION_NO_UNCALLED_BETS = (" Checks", " Fold", " Card dealt to a spot", " Big blind/Bring in")

    # translations from captured groups to fpdb info strings
    lim_blinds: ClassVar[dict[str, tuple[str, str]]] = {
        "0.04": ("0.01", "0.02"),
        "0.08": ("0.02", "0.04"),
        "0.10": ("0.02", "0.05"),
        "0.20": ("0.05", "0.10"),
        "0.25": ("0.05", "0.10"),
        "0.40": ("0.10", "0.20"),
        "0.50": ("0.10", "0.25"),
        "1.00": ("0.25", "0.50"),
        "1": ("0.25", "0.50"),
        "2.00": ("0.50", "1.00"),
        "2": ("0.50", "1.00"),
        "4.00": ("1.00", "2.00"),
        "4": ("1.00", "2.00"),
        "6.00": ("1.50", "3.00"),
        "6": ("1.50", "3.00"),
        "8.00": ("2.00", "4.00"),
        "8": ("2.00", "4.00"),
        "10.00": ("2.50", "5.00"),
        "10": ("2.50", "5.00"),
        "16.00": ("4.00", "8.00"),
        "16": ("4.00", "8.00"),
        "20.00": ("5.00", "10.00"),
        "20": ("5.00", "10.00"),
        "30.00": ("7.50", "15.00"),
        "30": ("7.50", "15.00"),
        "40.00": ("10.00", "20.00"),
        "40": ("10.00", "20.00"),
        "60.00": ("15.00", "30.00"),
        "60": ("15.00", "30.00"),
        "80.00": ("20.00", "40.00"),
        "80": ("20.00", "40.00"),
        "100.00": ("25.00", "50.00"),
        "100": ("25.00", "50.00"),
    }

    limits: ClassVar[dict[str, str]] = {"No Limit": "nl", "Pot Limit": "pl", "Fixed Limit": "fl", "Turbo": "nl"}
    games: ClassVar[dict[str, tuple[str, str]]] = {  # base, category
        "HOLDEM": ("hold", "holdem"),
        "OMAHA": ("hold", "omahahi"),
        "OMAHA HiLo": ("hold", "omahahilo"),
        "OMAHA_HL": ("hold", "omahahilo"),
        "7CARD": ("stud", "studhi"),
        "7CARD HiLo": ("stud", "studhilo"),
        "7CARD_HL": ("hold", "studhilo"),
        "HOLDEMZonePoker": ("hold", "holdem"),
        "OMAHAZonePoker": ("hold", "omahahi"),
        "OMAHA HiLoZonePoker": ("hold", "omahahilo"),
    }
    currencies: ClassVar[dict[str, str]] = {"$": "USD", "": "T$"}

    # Static regexes
    re_game_info: ClassVar[re.Pattern[str]] = re.compile(
        r"""
          (Ignition|Bovada|Bodog(\.com|\.eu|\sUK|\sCanada|88)?)\sHand\s\#C?(?P<HID>[0-9]+):?\s+
          ((?P<ZONE>Zone\sPoker\sID|TBL)\#(?P<TABLE>.+?)\s)?
          (?P<GAME>HOLDEM|OMAHA|OMAHA_HL|7CARD|7CARD\sHiLo|OMAHA\sHiLo|7CARD_HL|HOLDEMZonePoker|OMAHAZonePoker|OMAHA\sHiLoZonePoker)\s+
          (Tournament\s\#(M\-)?                # open paren of tournament info Tournament #2194767 TBL#1,
          (?P<TOURNO>\d+)\sTBL\#(?P<TABLENO>\d+),
          \s)?
          (?P<HU>1\son\s1\s)?
          (?P<LIMIT>No\sLimit|Fixed\sLimit|Pot\sLimit|Turbo)?
          (\s?Normal\s?)?
          (-\sLevel\s\d+?\s
          \(?                            # open paren of the stakes
          (?P<CURRENCY>{LS}|)?
          (?P<SB>[,.0-9]+)/({LS})?
          (?P<BB>[,.0-9]+)
          \s?(?P<ISO>{LEGAL_ISO})?
          \))?
          (\s\[(?P<VERSION>MVS)\])?
          \s-\s
          (?P<DATETIME>.*$)
        """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_player_info: ClassVar[re.Pattern[str]] = re.compile(
        r"""
          ^Seat\s(?P<SEAT>[0-9]+):\s
          {PLYR}\s(?P<HERO>\[ME\]\s)?
          \(({LS})?(?P<CASH>[{NUM}]+)\sin\schips\)""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_player_info_stud: ClassVar[re.Pattern[str]] = re.compile(
        r"""
         ^(?P<PNAME>Seat\+(?P<SEAT>[0-9]+))
         (?P<HERO>\s\[ME\])?:\s
         ({LS})?(?P<CASH>[{NUM}]+)\sin\schips""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_player_seat: ClassVar[re.Pattern[str]] = re.compile(r"^Seat\+(?P<SEAT>[0-9]+)", re.MULTILINE | re.VERBOSE)
    re_identify: ClassVar[re.Pattern[str]] = re.compile(
        r"(Ignition|Bovada|Bodog(\.com|\.eu|\sUK|\sCanada|88)?)\sHand",
    )
    re_split_hands: ClassVar[re.Pattern[str]] = re.compile("\n\n+")
    re_tail_split_hands: ClassVar[re.Pattern[str]] = re.compile("(\n\n\n+)")
    re_button: ClassVar[re.Pattern[str]] = re.compile(
        r"Dealer\s?:\s?Set\sdealer(\/Bring\sin\sspot)?\s\[(?P<BUTTON>\d+)\]",
        re.MULTILINE | re.VERBOSE,
    )
    re_board1: ClassVar[re.Pattern[str]] = re.compile(
        r"Board \[(?P<FLOP>\S\S\S? \S\S\S? \S\S\S?)?\s+?(?P<TURN>\S\S\S?)?\s+?(?P<RIVER>\S\S\S?)?\]",
    )
    re_board2: ClassVar[dict[str, re.Pattern[str]]] = {
        "FLOP": re.compile(r"\*\*\* FLOP \*\*\* \[(?P<CARDS>\S\S \S\S \S\S)\]"),
        "TURN": re.compile(
            r"\*\*\* TURN \*\*\* \[\S\S \S\S \S\S\] \[(?P<CARDS>\S\S)\]",
        ),
        "RIVER": re.compile(
            r"\*\*\* RIVER \*\*\* \[\S\S \S\S \S\S \S\S\] \[(?P<CARDS>\S\S)\]",
        ),
    }
    re_date_time: ClassVar[re.Pattern[str]] = re.compile(
        r"""(?P<Y>[0-9]{4})\-(?P<M>[0-9]{2})\-(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""",
        re.MULTILINE,
    )
    # These used to be compiled per player, but regression tests say
    # we don't have to, and it makes life faster.
    re_post_sb: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR} (\s?\[ME\]\s)?: (Ante\/Small (B|b)lind|Posts chip|Small (B|b)lind) "
        r"(?P<CURRENCY>{CUR})(?P<SB>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_post_bb: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR} (\s?\[ME\]\s)?: (Big (B|b)lind\/Bring in|Big (B|b)lind) (?P<CURRENCY>{CUR})(?P<BB>[{NUM}]+)".format(
            **substitutions,
        ),
        re.MULTILINE,
    )
    re_antes: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR} (\s?\[ME\]\s)?: Ante chip {CUR}(?P<ANTE>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_bring_in: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR} (\s?\[ME\]\s)?: (Bring_in chip|Big (B|b)lind\/Bring in|Bring in)\s?"
        r"(\(timeout\) )?{CUR}(?P<BRINGIN>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_post_both: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR} (\s?\[ME\]\s)?: Posts dead chip {CUR}(?P<SBBB>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_hero_cards: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR}  ?\[ME\] : Card dealt to a spot \[(?P<NEWCARDS>.+?)\]".format(**substitutions),
        re.MULTILINE,
    )
    re_action: ClassVar[re.Pattern[str]] = re.compile(
        r"""(?P<ACTION>
                        ^{PLYR}\s(\s?\[ME\]\s)?:(\sD)?(?P<ATYPE>\s(B|b)ets|\sDouble\sbets|\sChecks|\s(R|r)aises|\sCalls?|\sFold|\sBring_in\schip|\sBig\sblind\/Bring\sin|\sAll\-in(\((raise|raise\-timeout)\))?|\sCard\sdealt\sto\sa\sspot)
                        (\schip\sinfo)?(\(timeout\))?(\s{CUR}(?P<BET>[{NUM}]+)(\sto\s{CUR}(?P<BETTO>[{NUM}]+))?|\s\[(?P<NEWCARDS>.+?)\])?)""".format(
            **substitutions,
        ),
        re.MULTILINE | re.VERBOSE,
    )
    re_showdown_action: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR} (?P<HERO>\s?\[ME\]\s)?: Card dealt to a spot \[(?P<CARDS>.*)\]".format(**substitutions),
        re.MULTILINE,
    )
    re_collect_pot1: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR} (\s?\[ME\]\s)?: Hand (R|r)esult(\-Side (P|p)ot)? {CUR}(?P<POT1>[{NUM}]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_bounty: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR} (\s?\[ME\]\s)?: BOUNTY PRIZE \[{CUR}(?P<BOUNTY>[{NUM}]+)\]".format(**substitutions),
        re.MULTILINE,
    )
    re_dealt: ClassVar[re.Pattern[str]] = re.compile(
        r"^{PLYR} (\s?\[ME\]\s)?: Card dealt to a spot".format(**substitutions),
        re.MULTILINE,
    )
    re_buyin: ClassVar[re.Pattern[str]] = re.compile(
        r"(\s-\s\d+\s-\s(?P<TOURNAME>.+?))?\s-\s(?P<BUYIN>(?P<TICKET>TT)?(?P<BIAMT>[{LS}\d\.,]+)-(?P<BIRAKE>[{LS}\d\.,]+)?)\s-\s".format(
            **substitutions,
        ),
    )
    re_knockout: ClassVar[re.Pattern[str]] = re.compile(
        r"\s\((?P<BOUNTY>[{LS}\d\.,]+)\sKnockout".format(**substitutions),
    )
    re_stakes: ClassVar[re.Pattern[str]] = re.compile(
        r"(RING|ZONE|\w+)\s-\s(?P<CURRENCY>{LS}|)?(?P<SB>[{NUM}]+)-({LS})?(?P<BB>[{NUM}]+)".format(**substitutions),
    )
    re_summary: ClassVar[re.Pattern[str]] = re.compile(r"\*\*\*\sSUMMARY\s\*\*\*")
    re_hole_third: ClassVar[re.Pattern[str]] = re.compile(r"\*\*\*\s(3RD\sSTREET|HOLE\sCARDS)\s\*\*\*")
    re_return_bet: ClassVar[re.Pattern[str]] = re.compile(r"Return\suncalled\sportion", re.MULTILINE)
    re_rake: ClassVar[re.Pattern[str]] = re.compile(
        r"Total Pot\(\$(?P<POT>[\d.,]+)\).*?\| Rake \(\$(?P<RAKE>[\d.,]+)\)",
        re.MULTILINE,
    )
    re_pot_no_rake: ClassVar[re.Pattern[str]] = re.compile(
        r"Total Pot\(\$(?P<POT>[\d.,]+)\)\s*$",
        re.MULTILINE,
    )
    # Small Blind : Hand result $19

    def compilePlayerRegexs(self, hand: "Hand") -> None:  # noqa: ARG002
        """Compile player-specific regular expressions for pot collection parsing.

        This method updates the player regex patterns based on the current set of players,
        ensuring accurate parsing of pot collection lines for each player in the hand.

        Args:
            hand: The Hand object containing player information.
        """
        subst = self.substitutions
        players = set(self.playersMap.keys())
        if not players <= self.compiledPlayers:  # x <= y means 'x is subset of y'
            self.compiledPlayers = players
            subst["PLYR"] = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"
            self.re_collect_pot2 = re.compile(
                r"Seat[\+\s](?P<SEAT>[0-9]+):\s?{PLYR}"
                r"(\sHI)?\s({LS})?(?P<POT1>[{NUM}]+)?"
                r"(?P<STRING>[a-zA-Z\s]+)"
                r"(?P<CARDS1>\[[-a-zA-Z0-9\s]+\])"
                r"(\sLOW?\s({LS})?(?P<POT2>[{NUM}]+))?".format(**subst),
                re.MULTILINE,
            )

    def readSummaryInfo(self, summary_info_list: list[str]) -> bool:  # noqa: ARG002
        """Read and process summary information for a hand history file.

        This method logs entry and debug messages for summary info processing and always returns True.

        Args:
            summary_info_list: A list of summary information strings to process.

        Returns:
            bool: Always returns True.
        """
        log.info("enter method readSummaryInfo.")
        log.debug("Method readSummaryInfo non implemented.")
        return True

    def readSupportedGames(self) -> list[list[str]]:
        """Return a list of supported game types for the Bovada site.

        This method provides all combinations of game type, base, and limit supported by the parser.

        Returns:
            list[list[str]]: A list of supported game type, base, and limit combinations.
        """
        return [
            ["ring", "hold", "nl"],
            ["ring", "hold", "pl"],
            ["ring", "hold", "fl"],
            ["ring", "stud", "fl"],
            ["tour", "hold", "nl"],
            ["tour", "hold", "pl"],
            ["tour", "hold", "fl"],
            ["tour", "stud", "fl"],
        ]

    def parseHeader(self, hand_text: str, whole_file: str) -> dict[str, str]:
        """Parse the header of a hand history and extract game type information.

        This method determines the game type from the hand text and, for tournaments,
        calculates the maximum number of seats from the first hand in the file.

        Args:
            hand_text: The text of the hand history to parse.
            whole_file: The entire contents of the hand history file.

        Returns:
            dict[str, str]: A dictionary containing game type and related information.
        """
        gametype = self.determineGameType(hand_text)
        if gametype["type"] == "tour":
            handlist = re.split(self.re_split_hands, whole_file)
            result = re.findall(self.re_player_seat, handlist[0])
            gametype["maxSeats"] = len(result)
        return gametype

    def determineGameType(self, hand_text: str) -> dict[str, str]:
        """Determine the game type from the provided hand history text.

        This method validates the hand text, extracts game information, and builds a dictionary
        describing the game type, including limit, blinds, and currency.

        Args:
            hand_text: The text of the hand history to analyze.

        Returns:
            dict[str, str]: A dictionary containing game type and related information.
        """
        self._validateHandText(hand_text)
        mg = self._extractGameInfo(hand_text, self.in_path)
        info = self._buildGameTypeInfo(mg)
        self._adjustFixedLimitBlinds(info, mg, hand_text)
        return info

    def _validateHandText(self, hand_text: str) -> None:
        """Validate the structure of the provided hand history text.

        This method checks for required patterns in the hand text and raises an error if the
        hand history is incomplete or does not match expected formats.

        Args:
            hand_text: The text of the hand history to validate.

        Raises:
            FpdbParseError: If the hand text does not contain required game info.
            FpdbHandPartial: If the hand text appears to be a partial or incomplete hand history.
        """
        m = self.re_game_info.search(hand_text)
        if not m:
            tmp = hand_text[:200]
            log.error("BovadaToFpdb.determineGameType: '%s'", tmp)
            raise FpdbParseError

        m1 = self.re_dealt.search(hand_text)
        m2 = self.re_summary.split(hand_text)
        m3 = self.re_hole_third.split(hand_text)
        expected_summary_parts = 2
        max_hole_third_parts = 3
        if not m1 or len(m2) != expected_summary_parts or len(m3) > max_hole_third_parts:
            msg = "Partial hand history"
            raise FpdbHandPartial(msg)

    def _extractGameInfo(self, hand_text: str, in_path: str = "") -> dict[str, str]:
        """Extract game information from hand text and file path.

        This method searches the hand text and file path for game-related information,
        returning a dictionary of matched groups.

        Args:
            hand_text: The text of the hand history to search.
            in_path: The file path, used to extract additional game info if present.

        Returns:
            dict[str, str]: A dictionary containing extracted game information.
        """
        m = self.re_game_info.search(hand_text)
        mg = m.groupdict()
        if m := self.re_stakes.search(in_path):
            mg.update(m.groupdict())
        return mg

    def _buildGameTypeInfo(self, mg: dict[str, str]) -> dict[str, str]:
        """Build a dictionary describing the game type from extracted match groups.

        This method constructs a dictionary with limit type, game base, blinds, currency, and other
        relevant game information based on the provided match group dictionary.

        Args:
            mg: A dictionary of match groups extracted from the hand history.

        Returns:
            dict[str, str]: A dictionary containing structured game type information.
        """
        info = {}

        # Set limit type
        if "LIMIT" in mg:
            info["limitType"] = self.limits[mg["LIMIT"]] if mg["LIMIT"] else "nl"

        # Set game base and category
        if "GAME" in mg:
            (info["base"], info["category"]) = self.games[mg["GAME"]]

        # Initialize blinds as None
        info["sb"] = None
        info["bb"] = None
        
        # Set blinds if available
        if "SB" in mg and mg["SB"]:
            info["sb"] = self.clearMoneyString(mg["SB"])
        if "BB" in mg and mg["BB"]:
            info["bb"] = self.clearMoneyString(mg["BB"])

        # Set tournament vs ring
        if "TOURNO" in mg and mg["TOURNO"] is not None:
            info["type"] = "tour"
            info["currency"] = "T$"
        else:
            info["type"] = "ring"
            info["currency"] = "USD"

        # Set currency
        if "CURRENCY" in mg and mg["CURRENCY"] is not None:
            info["currency"] = self.currencies[mg["CURRENCY"]]

        # Set fast flag
        info["fast"] = "Zone" in mg["GAME"]
        
        # Set split flag (Bovada doesn't have split pot games like Hi/Lo)
        info["split"] = False

        return info

    def _adjustFixedLimitBlinds(self, info: dict[str, str], mg: dict[str, str], hand_text: str) -> None:
        """Adjust small and big blinds for fixed limit games.

        This method updates the small and big blind values in the info dictionary for fixed limit
        games, using standard mappings for ring games or recalculating for tournaments.

        Args:
            info: The dictionary containing game type information to update.
            mg: The dictionary of match groups extracted from the hand history.
            hand_text: The text of the hand history, used for error logging.

        Raises:
            FpdbParseError: If blinds cannot be determined from the provided information.
        """
        # If blinds are not set, try to extract them from hand content
        if info["sb"] is None or info["bb"] is None:
            self._extractBlindsFromContent(info, hand_text)
            
        if info["limitType"] == "fl" and info["bb"] is not None:
            if info["type"] == "ring":
                try:
                    info["sb"] = self.lim_blinds[info["bb"]][0]
                    info["bb"] = self.lim_blinds[info["bb"]][1]
                except KeyError:
                    tmp = hand_text[:200]
                    log.exception("lim_blinds has no lookup for '%s' - '%s'", mg.get("BB", ""), tmp)
                    raise FpdbParseError from None
            else:
                info["sb"] = str((Decimal(info["sb"]) / 2).quantize(Decimal("0.01")))
                
    def _extractBlindsFromContent(self, info: dict[str, str], hand_text: str) -> None:
        """Extract blind values from hand content when not in header or filename.
        
        Args:
            info: The dictionary containing game type information to update.
            hand_text: The text of the hand history to search for blind information.
        """
        # Look for "Small Blind : Ante/Small Blind $X.XX"
        if sb_match := re.search(r"Small Blind\s*:\s*.*?\$([0-9.]+)", hand_text):
            if info["sb"] is None:
                info["sb"] = self.clearMoneyString(sb_match.group(1))
                
        # Look for "Big Blind : Big blind/Bring in $X.XX"  
        if bb_match := re.search(r"Big Blind\s*:\s*.*?\$([0-9.]+)", hand_text):
            if info["bb"] is None:
                info["bb"] = self.clearMoneyString(bb_match.group(1))
                
        # For Stud games, sb/bb are not applicable (they use antes and bring-in)
        # Leave sb/bb as None for Stud games

    def readHandInfo(self, hand: "Hand") -> None:
        """Read and process hand information from the hand text.

        This method extracts hand information, sets the hand speed, and processes key attributes
        to populate the Hand object with relevant details.

        Args:
            hand: The Hand object to populate with extracted information.
        """
        info = self._extractHandInfo(hand)
        self._setHandSpeed(hand)
        self._processHandInfoKeys(hand, info)

    def _extractHandInfo(self, hand: "Hand") -> dict[str, str]:
        """Extract detailed hand information from the hand text and file path.

        This method searches the hand text and file path for relevant hand information,
        including game details, buy-in, and knockout data, and returns a dictionary of results.

        Args:
            hand: The Hand object containing the hand history text.

        Returns:
            dict[str, str]: A dictionary containing extracted hand information.

        Raises:
            FpdbParseError: If required game information is not found in the hand text.
        """
        info = {}
        m = self.re_game_info.search(hand.handText)
        if m is None:
            tmp = hand.handText[:200]
            log.error("readHandInfo not found: '%s'", tmp)
            raise FpdbParseError

        info |= m.groupdict()
        if m := self.re_buyin.search(self.in_path):
            info |= m.groupdict()
        hand.allInBlind = False
        if m2 := self.re_knockout.search(self.in_path):
            info |= m2.groupdict()
        return info

    def _setHandSpeed(self, hand: "Hand") -> None:
        """Extract detailed hand information from the hand text and file path.

        This method searches the hand text and file path for relevant hand information,
        including game details, buy-in, and knockout data, and returns a dictionary of results.

        Args:
            hand: The Hand object containing the hand history text.

        Returns:
            dict[str, str]: A dictionary containing extracted hand information.

        Raises:
            FpdbParseError: If required game information is not found in the hand text.
        """
        if "Hyper Turbo" in self.in_path:
            hand.speed = "Hyper"
        elif "Turbo" in self.in_path:
            hand.speed = "Turbo"

    def _processHandInfoKeys(self, hand: "Hand", info: dict[str, str]) -> None:
        """Process and assign key hand information from the extracted info dictionary.

        This method iterates through the info dictionary and sets corresponding attributes
        on the Hand object, such as hand ID, tournament number, buy-in, table, max seats, and version.

        Args:
            hand: The Hand object to update with extracted information.
            info: A dictionary containing hand information key-value pairs.
        """
        for key, value in info.items():
            match key:
                case "DATETIME":
                    self._process_datetime(hand, value)
                case "HID":
                    hand.handid = value
                case "TOURNO":
                    hand.tourNo = value
                case "BUYIN" if info["TOURNO"] is not None:
                    self._process_buyin(hand, info)
                case "TABLE":
                    self._process_table(hand, info)
                case "MAX" if value is not None:
                    hand.maxseats = int(value)
                case "HU" if value is not None:
                    hand.maxseats = 2
                case "VERSION":
                    hand.version = value

        hand.maxseats = hand.maxseats or 9
        hand.version = hand.version or "LEGACY"

    def _process_datetime(self, hand: "Hand", datetime_str: str) -> None:
        """Process and assign the hand's start time from a datetime string.

        This method parses the provided datetime string, converts it to UTC, and sets the hand's start time.

        Args:
            hand: The Hand object whose start time will be set.
            datetime_str: The datetime string to parse and convert.
        """
        m1 = self.re_date_time.finditer(datetime_str)
        datetimestr = "2000/01/01 00:00:00"  # default used if time not found
        for a in m1:
            datetimestr = f"{a.group('Y')}/{a.group('M')}/{a.group('D')} {a.group('H')}:{a.group('MIN')}:{a.group('S')}"

        # Parse datetime and let changeTimezone handle timezone conversion
        naive_dt = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S")
        hand.startTime = HandHistoryConverter.changeTimezone(naive_dt, "ET", "UTC")

    def _process_buyin(self, hand: "Hand", info: dict[str, str]) -> None:
        """Process and assign buy-in, fee, and bounty information for a hand.

        This method determines the buy-in amount, fee, currency, and knockout bounty for the hand,
        updating the Hand object with the extracted values.

        Args:
            hand: The Hand object to update with buy-in and fee information.
            info: A dictionary containing buy-in and related information.

        Raises:
            FpdbParseError: If the currency cannot be determined from the buy-in value.
        """
        buyin_value = info["BUYIN"]

        if buyin_value == "Freeroll":
            hand.buyin = 0
            hand.fee = 0
            hand.buyinCurrency = "FREE"
            return

        # Detect currency
        if "$" in buyin_value:
            hand.buyinCurrency = "USD"
        elif re.match("^[0-9+]*$", buyin_value):
            hand.buyinCurrency = "play"
        else:
            log.error(
                "Failed to detect currency. Hand ID: %s: '%s'",
                hand.handid,
                buyin_value,
            )
            raise FpdbParseError

        # Process bounty
        if info.get("BOUNTY") is not None:
            bounty_cleaned = self.clearMoneyString(info["BOUNTY"].strip("$"))
            hand.koBounty = int(100 * Decimal(bounty_cleaned))
            hand.isKO = True
        else:
            hand.isKO = False

        # Process buy-in amount and rake
        biamt_cleaned = self.clearMoneyString(info["BIAMT"].strip("$"))
        birake_cleaned = self.clearMoneyString(info["BIRAKE"].strip("$")) if info["BIRAKE"] else "0"

        if info["TICKET"] is None:
            hand.buyin = int(100 * Decimal(biamt_cleaned))
            hand.fee = int(100 * Decimal(birake_cleaned))
        else:
            hand.buyin = 0
            hand.fee = 0

    def _process_table(self, hand: "Hand", info: dict[str, str]) -> None:
        """Process and assign the table name for the hand.

        This method sets the hand's table name based on available information in the info dictionary.

        Args:
            hand: The Hand object to update with the table name.
            info: A dictionary containing table-related information.
        """
        if info.get("TABLENO"):
            hand.tablename = info["TABLENO"]
        elif info.get("ZONE") and "Zone" in info["ZONE"]:
            hand.tablename = f"{info['ZONE']} {info['TABLE']}"
        else:
            hand.tablename = info["TABLE"]

    def readButton(self, hand: "Hand") -> None:
        """Read and assign the dealer button position for the hand.

        This method searches the hand text for the dealer button and sets the button position on the Hand object.

        Args:
            hand: The Hand object to update with the button position.
        """
        if m := self.re_button.search(hand.handText):
            hand.buttonpos = int(m.group("BUTTON"))

    def readPlayerStacks(self, hand: "Hand") -> None:
        """Read and assign player stack information from the hand text.

        This method parses the hand text to extract player names, seats, and stack sizes,
        updating the Hand object with player information and setting the button position if found.

        Args:
            hand: The Hand object to update with player stack information.

        Raises:
            FpdbParseError: If no players are found in the hand text.
        """
        self.playersMap, seat_no = {}, 1
        if hand.gametype["base"] in ("stud"):
            m = self.re_player_info_stud.finditer(hand.handText)
        else:
            m = self.re_player_info.finditer(hand.handText)
        for a in m:
            if (
                re.search(
                    rf"{re.escape(a.group('PNAME'))} (\s?\[ME\]\s)?: Card dealt to a spot",
                    hand.handText,
                )
                or hand.version == "MVS"
            ):
                if not hand.buttonpos and a.group("PNAME") == "Dealer":
                    hand.buttonpos = int(a.group("SEAT"))
                if a.group("HERO"):
                    self.playersMap[a.group("PNAME")] = "Hero"
                else:
                    self.playersMap[a.group("PNAME")] = f"Seat {a.group('SEAT')}"
                hand.addPlayer(
                    seat_no,
                    self.playersMap[a.group("PNAME")],
                    self.clearMoneyString(a.group("CASH")),
                )
            seat_no += 1
        if len(hand.players) == 0:
            tmp = hand.handText[:200]
            log.error("readPlayerStacks failed: '%s'", tmp)
            raise FpdbParseError
        max_full_ring_players = 10
        if len(hand.players) == max_full_ring_players:
            hand.maxseats = max_full_ring_players

    def playerSeatFromPosition(self, source: str, handid: str, position: str) -> str:
        """Return the player name or seat corresponding to a given position.

        This method looks up the player in the playersMap using the provided position and returns the player name.
        Raises an error if the player cannot be found.

        Args:
            source: The source or context of the lookup, used for error logging.
            handid: The hand ID, used for error logging.
            position: The position string to look up in the playersMap.

        Returns:
            str: The player name or seat corresponding to the given position.

        Raises:
            FpdbParseError: If the player cannot be found for the given position.
        """
        player = self.playersMap.get(position)
        if player is None:
            log.error(
                "Hand.%s: '%s' unknown player seat from position: '%s'",
                source,
                handid,
                position,
            )
            raise FpdbParseError
        return player

    def _get_initial_street_info(self, hand: "Hand") -> tuple[str, str]:
        """Determine the initial street information for the hand.

        This method returns the appropriate starting street names based on the game type.

        Args:
            hand: The Hand object containing game type information.

        Returns:
            tuple[str, str]: A tuple with the initial street and first street names.
        """
        if hand.gametype["base"] == "hold":
            return "PREFLOP", "PREFLOP"
        return "THIRD", "THIRD"

    def _process_street_action(
        self, action: "re.Match[str]", streetno: int, contenders: int, bets: int,
    ) -> tuple[int, int, int, int]:
        """Process a single action and update street and player state.

        This method interprets the action type, updates the number of contenders, bets, and street actions,
        and returns the updated state for further processing.

        Args:
            action: The regex match object representing the action.
            streetno: The current street number.
            contenders: The number of players still in contention.
            bets: The number of bets made so far.

        Returns:
            tuple[int, int, int, int]: Updated values for streetactions, players, contenders, and bets.
        """
        streetactions = 0
        players = contenders

        atype = action.group("ATYPE")

        if atype == " Fold":
            contenders -= 1
        elif atype in (" Raises", " raises"):
            if streetno == 1:
                bets = 1
            streetactions, players = 0, contenders
        elif atype in (" Bets", " bets", " Double bets"):
            streetactions, players, bets = 0, contenders, 1
        elif atype in (" All-in(raise)", "All-in(raise-timeout)"):
            streetactions, players = 0, contenders
            contenders -= 1
        elif atype == " All-in":
            if bets == 0 and streetno > 1:
                streetactions, players, bets = 0, contenders, 1
            contenders -= 1

        return streetactions, players, contenders, bets

    def _should_count_action(self, action: "re.Match[str]", hand: "Hand") -> bool:
        """Determine whether an action should be counted for street processing.

        This method checks the action type and game type to decide if the action should be included
        in the count of actions for the current street.

        Args:
            action: The regex match object representing the action.
            hand: The Hand object containing game type information.

        Returns:
            bool: True if the action should be counted, False otherwise.
        """
        atype = action.group("ATYPE")
        return (atype != " Card dealt to a spot" and
                (atype != " Big blind/Bring in" or hand.gametype["base"] == "stud"))

    def _process_board_cards(self, hand: "Hand") -> None:
        """Process and assign board cards for the hand.

        This method extracts community cards for each street and updates the hand's streets dictionary
        with the found board cards, if applicable for the game type.

        Args:
            hand: The Hand object to update with board card information.
        """
        if hand.gametype["base"] != "hold":
            return

        if hand.gametype["fast"]:
            for street in ("FLOP", "TURN", "RIVER"):
                m1 = self.re_board2[street].search(hand.handText)
                if m1 and m1.group("CARDS") and not hand.streets.get(street):
                    hand.streets[street] = m1.group("CARDS")
        else:
            m1 = self.re_board1.search(hand.handText)
            for street in ("FLOP", "TURN", "RIVER"):
                if m1 and m1.group(street) and not hand.streets.get(street):
                    hand.streets[street] = m1.group(street)

    def markStreets(self, hand: "Hand") -> None:
        """Mark and process the action streets for a hand.

        This method uses street delimiters to split hand history into sections
        and assigns actions to appropriate streets.

        Args:
            hand: The Hand object to update with street and action information.
        """
        # Split hand text by street markers
        if hand.gametype["base"] == "hold":
            # For Hold'em games, use standard street markers
            street_splits = re.split(r'\*\*\* (HOLE CARDS|FLOP|TURN|RIVER|SUMMARY) \*\*\*', hand.handText)
            
            # Map sections to streets based on position in split
            street_mapping = {
                2: "PREFLOP",  # Section after HOLE CARDS
                4: "FLOP",     # Section after FLOP
                6: "TURN",     # Section after TURN  
                8: "RIVER",    # Section after RIVER
            }
            
            for section_idx, street in street_mapping.items():
                if section_idx < len(street_splits):
                    content = street_splits[section_idx].strip()
                    if content:
                        hand.streets[street] = content
        else:
            # For Stud games, use the original complex logic
            self._markStreetsComplex(hand)

        # Process board cards
        self._process_board_cards(hand)
        
    def _markStreetsComplex(self, hand: "Hand") -> None:
        """Original complex logic for marking streets, used for Stud games."""
        street, firststreet = self._get_initial_street_info(hand)

        # Count all-in blinds
        m = self.re_action.finditer(self.re_hole_third.split(hand.handText)[0])
        allinblind = sum(action.group("ATYPE") == " All-in" for action in m)

        # Process main actions
        m = self.re_action.finditer(self.re_hole_third.split(hand.handText)[-1])
        dealt_in = len(hand.players) - allinblind
        streetactions, streetno, players, contenders, bets, acts = (
            0, 1, dealt_in, 0, dealt_in, None,
        )

        for action in m:
            if action.groupdict() != acts or streetactions == 0:
                acts = action.groupdict()

                # Process the action
                new_streetactions, new_players, contenders, bets = self._process_street_action(
                    action, streetno, contenders, bets,
                )
                if new_streetactions == 0:  # Action resets street
                    streetactions, players = new_streetactions, new_players

                # Count action if applicable
                if self._should_count_action(action, hand):
                    streetactions += 1

                hand.streets[street] += action.group("ACTION") + "\n"

                # Check if street is complete
                if streetactions == players:
                    streetno += 1
                    if streetno < len(hand.actionStreets):
                        street = hand.actionStreets[streetno]
                    streetactions, players, bets = 0, contenders, 0

        # Set default street if none found
        if not hand.streets.get(firststreet):
            hand.streets[firststreet] = hand.handText
            
    def _process_board_cards(self, hand: "Hand") -> None:
        """Extract and process board cards from street content, separating them from actions."""
        if hand.gametype["base"] == "hold":
            # Extract board cards from street content and keep actions separate
            for street in ["FLOP", "TURN", "RIVER"]:
                if street in hand.streets and hand.streets[street].strip():
                    content = hand.streets[street]
                    
                    # Look for board cards pattern like [2c Qc 7h] or [2c Qc 7h] [Ac]
                    board_matches = re.findall(r'\[([2-9TJQKA][chsd]\s*)+\]', content)
                    if board_matches:
                        # Extract actions (everything that's not board cards)
                        actions_content = re.sub(r'\s*\[([2-9TJQKA][chsd]\s*)+\]', '', content)
                        hand.streets[street] = actions_content.strip()
                        
                        # Store the board cards (just for debugging, readCommunityCards will handle them)
                        board_cards = ' '.join(board_matches).replace('[', '').replace(']', '')
                        # Could store board_cards somewhere if needed

    def readCommunityCards(
        self,
        hand: "Hand",
        street: str,
    ) -> None:
        """Read and assign community cards for a given street.

        This method extracts community cards for the specified street from the hand text
        and updates the Hand object with the found cards.

        Args:
            hand: The Hand object to update with community card information.
            street: The street name (e.g., "FLOP", "TURN", "RIVER") to extract cards for.
        """
        if hand.gametype["fast"]:
            m = self.re_board2[street].search(hand.handText)
            if m and m.group("CARDS"):
                hand.setCommunityCards(street, m.group("CARDS").split(" "))
        elif street in {
            "FLOP",
            "TURN",
            "RIVER",
        }:  # a set of streets which get dealt community cards (i.e. all but PREFLOP)
            m = self.re_board1.search(hand.handText)
            if m and m.group(street):
                cards = m.group(street).split(" ")
                hand.setCommunityCards(street, cards)

    def readAntes(self, hand: "Hand") -> None:
        """Read and assign ante information for the hand.

        This method parses the hand text to extract ante amounts for each player and updates
        the Hand object with the corresponding ante values.

        Args:
            hand: The Hand object to update with ante information.
        """
        antes = None
        m = self.re_antes.finditer(hand.handText)
        for a in m:
            if a.groupdict() != antes:
                antes = a.groupdict()
                player = self.playerSeatFromPosition(
                    "BovadaToFpdb.readAntes",
                    hand.handid,
                    antes["PNAME"],
                )
                hand.addAnte(player, self.clearMoneyString(antes["ANTE"]))

    def readBringIn(self, hand: "Hand") -> None:
        """Read and assign bring-in information for the hand.

        This method parses the hand text to extract bring-in amounts and updates the Hand object
        with the bring-in value for the appropriate player. It also sets default blinds if not present.

        Args:
            hand: The Hand object to update with bring-in information.
        """
        if m := self.re_bring_in.search(hand.handText, re.DOTALL):
            player = self.playerSeatFromPosition(
                "BovadaToFpdb.readBringIn",
                hand.handid,
                m.group("PNAME"),
            )
            hand.addBringIn(player, self.clearMoneyString(m.group("BRINGIN")))

        if hand.gametype["sb"] is None and hand.gametype["bb"] is None:
            hand.gametype["sb"] = "1"
            hand.gametype["bb"] = "2"

    def _process_small_blinds(self, hand: "Hand") -> None:
        """Process and assign small blind posts for the hand.

        This method parses the hand text to extract small blind posts, updates the Hand object
        with small blind information, and sets the small blind value in the game type if not already set.

        Args:
            hand: The Hand object to update with small blind information.
        """
        postsb = None
        for a in self.re_post_sb.finditer(hand.handText):
            if postsb != a.groupdict():
                postsb = a.groupdict()
                player = self.playerSeatFromPosition(
                    "BovadaToFpdb.readBlinds.postSB",
                    hand.handid,
                    postsb["PNAME"],
                )
                hand.addBlind(
                    player,
                    "small blind",
                    self.clearMoneyString(postsb["SB"]),
                )
                if not hand.gametype["sb"]:
                    hand.gametype["sb"] = self.clearMoneyString(postsb["SB"])
            self.allInBlind(hand, "PREFLOP", a)

    def _detect_currency(self, currency_str: str) -> str:
        """Detect the currency type from a currency string.

        This method returns 'USD' if the string contains a dollar sign, 'play' for play money,
        or None if the currency cannot be determined.

        Args:
            currency_str: The string to analyze for currency type.

        Returns:
            str: The detected currency type ('USD', 'play', or None).
        """
        return "USD" if "$" in currency_str else "play" if re.match("^[0-9+]*$", currency_str) else None

    def _process_big_blinds(self, hand: "Hand") -> None:
        """Process and assign big blind posts for the hand.

        This method parses the hand text to extract big blind posts, updates the Hand object
        with big blind information, sets the big blind value in the game type if not already set,
        and detects the currency if not already specified.

        Args:
            hand: The Hand object to update with big blind information.
        """
        postbb = None
        for a in self.re_post_bb.finditer(hand.handText):
            if postbb != a.groupdict():
                postbb = a.groupdict()
                player = self.playerSeatFromPosition(
                    "BovadaToFpdb.readBlinds.postBB",
                    hand.handid,
                    "Big Blind",
                )
                hand.addBlind(player, "big blind", self.clearMoneyString(postbb["BB"]))
                self.allInBlind(hand, "PREFLOP", a)
                if not hand.gametype["bb"]:
                    hand.gametype["bb"] = self.clearMoneyString(postbb["BB"])
                if not hand.gametype["currency"] and (currency := self._detect_currency(postbb["CURRENCY"])):
                    hand.gametype["currency"] = currency

    def _is_heads_up_dealer_small_blind(self, player_name: str, hand: "Hand") -> bool:
        """Determine if the dealer is also the small blind in a heads-up game.

        This method checks if the given player is the dealer and if the hand is heads-up,
        returning True if the dealer is the small blind in this scenario.

        Args:
            player_name: The name of the player to check.
            hand: The Hand object containing player information.

        Returns:
            bool: True if the dealer is the small blind in a heads-up game, False otherwise.
        """
        heads_up_players = 2
        return player_name == "Dealer" and len(hand.players) == heads_up_players

    def _process_all_in_actions(self, hand: "Hand") -> None:
        """Process and assign all-in actions for the hand.

        This method parses the hand text to extract all-in actions, updating the Hand object
        with appropriate blind or ante information based on the action type and player.

        Args:
            hand: The Hand object to update with all-in action information.
        """
        acts = None
        for a in self.re_action.finditer(self.re_hole_third.split(hand.handText)[0]):
            if acts != a.groupdict():
                acts = a.groupdict()
                if acts["ATYPE"] == " All-in":
                    re_ante_plyr = re.compile(
                        rf"^{re.escape(acts['PNAME'])} (\s?\[ME\]\s)?: Ante chip "
                        rf"{self.substitutions['CUR']}(?P<ANTE>[{self.substitutions['NUM']}]+)",
                        re.MULTILINE,
                    )
                    m = self.re_antes.search(hand.handText)
                    if m1 := re_ante_plyr.search(hand.handText):
                        player = self.playerSeatFromPosition(
                            "BovadaToFpdb.readBlinds.postBB",
                            hand.handid,
                            acts["PNAME"],
                        )
                        if acts["PNAME"] == "Big Blind":
                            hand.addBlind(
                                player,
                                "big blind",
                                self.clearMoneyString(acts["BET"]),
                            )
                            self.allInBlind(hand, "PREFLOP", a)
                        elif (acts["PNAME"] == "Small Blind" or
                                self._is_heads_up_dealer_small_blind(acts["PNAME"], hand)):
                            hand.addBlind(
                                player,
                                "small blind",
                                self.clearMoneyString(acts["BET"]),
                            )
                            self.allInBlind(hand, "PREFLOP", a)
                    elif m:
                        player = self.playerSeatFromPosition(
                            "BovadaToFpdb.readAntes",
                            hand.handid,
                            acts["PNAME"],
                        )
                        hand.addAnte(player, self.clearMoneyString(acts["BET"]))
                        self.allInBlind(hand, "PREFLOP", a)

    def _process_both_blinds(self, hand: "Hand") -> None:
        """Process and assign both blinds for the hand.

        This method parses the hand text to extract posts where a player posts both blinds,
        updating the Hand object with the appropriate blind information.

        Args:
            hand: The Hand object to update with both blind information.
        """
        both = None
        for a in self.re_post_both.finditer(hand.handText):
            if both != a.groupdict():
                both = a.groupdict()
                player = self.playerSeatFromPosition(
                    "BovadaToFpdb.readBlinds.postBoth",
                    hand.handid,
                    both["PNAME"],
                )
                hand.addBlind(player, "both", self.clearMoneyString(both["SBBB"]))
                self.allInBlind(hand, "PREFLOP", a)

    def readBlinds(self, hand: "Hand") -> None:
        """Read and assign blind information for the hand.

        This method processes the hand text to extract and assign small blinds, big blinds,
        all-in actions, and both blinds, updating the Hand object accordingly.

        Args:
            hand: The Hand object to update with blind information.
        """
        if not self.re_return_bet.search(hand.handText):
            hand.setUncalledBets(True)

        self._process_small_blinds(hand)
        self._process_big_blinds(hand)
        self._process_all_in_actions(hand)
        self.fixBlinds(hand)
        self._process_both_blinds(hand)

    def fixBlinds(self, hand: "Hand") -> None:
        """Fix and assign small and big blind values for the hand.

        This method ensures that the hand has valid small and big blind values by checking the game type,
        attempting to infer missing values from known blind structures or the filename, and updating the Hand object.

        Args:
            hand: The Hand object to update with fixed blind values.

        Raises:
            FpdbParseError: If blinds cannot be determined or fixed.
        """
        if hand.gametype["sb"] is None and hand.gametype["bb"] is not None:
            big_blind = str(Decimal(hand.gametype["bb"]) * 2)
            if self.lim_blinds.get(big_blind) is not None:
                hand.gametype["sb"] = self.lim_blinds.get(big_blind)[0]
        elif hand.gametype["bb"] is None and hand.gametype["sb"] is not None:
            for v in list(self.lim_blinds.values()):
                if hand.gametype["sb"] == v[0]:
                    hand.gametype["bb"] = v[1]

        # Special handling for problematic hands - use filename to determine blinds
        if hand.gametype["sb"] is None or hand.gametype["bb"] is None:
            # Try to extract blinds from filename
            if filename_blinds := self._extractBlindsFromFilename():
                hand.gametype["sb"] = filename_blinds[0]
                hand.gametype["bb"] = filename_blinds[1]
                log.debug(
                    "Fixed blinds from filename for hand %s: sb=%s, bb=%s",
                    hand.handid,
                    hand.gametype["sb"],
                    hand.gametype["bb"],
                )
            else:
                log.error("Failed to fix blinds Hand ID: %s", hand.handid)
                raise FpdbParseError

        hand.sb = hand.gametype["sb"]
        hand.bb = hand.gametype["bb"]

    def _extractBlindsFromFilename(self) -> tuple[str, str] | None:
        """Extract small and big blind values from the input filename.

        This method attempts to parse the filename for blind structures in the format "$X-$Y"
        and returns the corresponding small and big blind values if found in the lim_blinds dictionary.

        Returns:
            tuple[str, str] | None: A tuple of (small_blind, big_blind) if found, otherwise None.
        """
        if not hasattr(self, "in_path") or not self.in_path:
            return None

        from pathlib import Path

        filename = Path(self.in_path).name

        # Pattern to match blinds in filename like "$8-$16" or "$30-$60"
        import re

        # Pattern to match blinds in filename like "$8-$16" or "$30-$60"
        if match := re.search(r"\$(\d+(?:\.\d+)?)-\$(\d+(?:\.\d+)?)", filename):
            # Extract the limit structure from filename
            # For "$8-$16", the key is "16" (the higher value)
            # For "$30-$60", the key is "60" (the higher value)
            limit_key = match[2]

            # Look up in lim_blinds dictionary
            if limit_key in self.lim_blinds:
                return self.lim_blinds[limit_key]  # Return (small_blind, big_blind)

            # Also try with ".00" suffix for exact match
            limit_key_with_decimals = f"{limit_key}.00"
            if limit_key_with_decimals in self.lim_blinds:
                return self.lim_blinds[limit_key_with_decimals]

        return None

    def readSTP(self, hand: "Hand") -> None:
        """Read STP (Short-Deck Poker) information for the hand.

        This method processes the hand text to extract and assign any relevant STP-specific information,
        updating the Hand object accordingly.

        Args:
            hand: The Hand object to update with STP information.
        """

    def _process_hero_cards(self, hand: "Hand") -> None:
        """Process and assign hero cards for the hand.

        This method iterates through the relevant streets and updates the Hand object with the hero's hole cards
        if found in the hand text.

        Args:
            hand: The Hand object to update with hero card information.
        """
        for street in ("PREFLOP", "DEAL"):
            if street in hand.streets:
                found_dict = None
                m = self.re_hero_cards.finditer(hand.handText)
                for found in m:
                    if found.groupdict() != found_dict:
                        found_dict = found.groupdict()
                        hand.hero = "Hero"
                        newcards = found.group("NEWCARDS").split(" ")
                        hand.addHoleCards(
                            street,
                            hand.hero,
                            closed=newcards,
                            shown=False,
                            mucked=False,
                            dealt=True,
                        )

    def _process_stud_hero_cards(self, hand: "Hand", street: str, player: str, newcards: list) -> None:
        """Process and assign hero cards for stud games.

        This method updates the Hand object with the hero's dealt cards for stud games,
        assigning closed and open cards based on the number of cards provided.

        Args:
            hand: The Hand object to update with hero card information.
            street: The street name where the cards are dealt.
            player: The player receiving the cards.
            newcards: List of new cards dealt to the player.
        """
        hand.hero = "Hero"
        hand.dealt.add(player)
        min_stud_cards = 3
        if len(newcards) >= min_stud_cards:
            hand.addHoleCards(
                street,
                player,
                closed=newcards[:2],
                open=[newcards[2]],
                shown=False,
                mucked=False,
                dealt=False,
            )
        else:
            hand.addHoleCards(
                street,
                player,
                closed=newcards,
                open=[],
                shown=False,
                mucked=False,
                dealt=False,
            )

    def _process_showdown_cards(self, hand: "Hand") -> None:
        """Process and assign showdown cards for the hand.

        This method iterates through each street and updates the Hand object with cards shown at showdown,
        handling both stud and non-stud games as appropriate.

        Args:
            hand: The Hand object to update with showdown card information.
        """
        for street, text in list(hand.streets.items()):
            if not text or street in ("PREFLOP", "DEAL"):
                continue

            m = self.re_showdown_action.finditer(hand.streets[street])
            found_dict = None
            for found in m:
                if found_dict != found.groupdict():
                    found_dict = found.groupdict()
                    player = self.playerSeatFromPosition(
                        "BovadaToFpdb.readHoleCards",
                        hand.handid,
                        found.group("PNAME"),
                    )

                    if street != "SEVENTH" or found.group("HERO"):
                        newcards = found.group("CARDS").split(" ")
                        oldcards = []
                    else:
                        oldcards = found.group("CARDS").split(" ")
                        newcards = []

                    if street == "THIRD" and found.group("HERO"):
                        self._process_stud_hero_cards(hand, street, player, newcards)
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

    def readHoleCards(self, hand: "Hand") -> None:
        """Process and assign showdown cards for the hand.

        This method iterates through each street and updates the Hand object with cards shown at showdown,
        handling both stud and non-stud games as appropriate.

        Args:
            hand: The Hand object to update with showdown card information.
        """
        self._process_hero_cards(hand)
        self._process_showdown_cards(hand)

    def readAction(self, hand: "Hand", street: str) -> None:
        """Read and assign player actions for a given street.

        This method processes the hand text to extract and assign player actions for the specified street,
        updating the Hand object with the corresponding action information.

        Args:
            hand: The Hand object to update with action information.
            street: The street name to extract actions for.
        """
        acts = None
        m = self.re_action.finditer(hand.streets[street])
        for action in m:
            if acts != action.groupdict():
                acts = action.groupdict()
                player = self.playerSeatFromPosition(
                    "BovadaToFpdb.readAction",
                    hand.handid,
                    action.group("PNAME"),
                )
                self._handle_uncalled_bets(hand, action)
                self._process_action(hand, street, player, action)

    def _handle_uncalled_bets(self, hand: "Hand", action: re.Match[str]) -> None:
        """Handle uncalled bets for the hand.

        This method checks the action type and updates the Hand object to indicate whether there are uncalled bets,
        based on the current action and all-in blind status.

        Args:
            hand: The Hand object to update with uncalled bet information.
            action: The regex match object representing the current action.
        """
        if (
            action.group("ATYPE") not in self.ACTION_NO_UNCALLED_BETS
            and not hand.allInBlind
        ):
            hand.setUncalledBets(False)

    def _process_action(self, hand: "Hand", street: str, player: str, action: re.Match[str]) -> None:
        """Process and assign a specific player action for a given street.

        This method determines the type of action and updates the Hand object accordingly,
        handling folds, checks, calls, raises, bets, all-ins, and ignored actions.

        Args:
            hand: The Hand object to update with action information.
            street: The street name where the action occurs.
            player: The player performing the action.
            action: The regex match object representing the current action.
        """
        action_type = action.group("ATYPE")

        if action_type in (self.ACTION_BRING_IN, *self.ACTION_IGNORED):
            # Bring-in and ignored actions require no processing
            return

        if action_type == self.ACTION_FOLD:
            hand.addFold(street, player)
        elif action_type == self.ACTION_CHECK:
            hand.addCheck(street, player)
        elif action_type in (self.ACTION_CALL, self.ACTION_CALL_ALT):
            self._handle_call_action(hand, street, player, action)
        elif action_type in self.ACTION_RAISES:
            self._handle_raise_action(hand, street, player, action)
        elif action_type in self.ACTION_BETS:
            self._handle_bet_action(hand, street, player, action)
        elif action_type == self.ACTION_ALLIN:
            self._handle_allin_action(hand, street, player, action)
        else:
            log.debug("Unimplemented readAction: '%s' '%s'", action.group("PNAME"), action_type)


    def _handle_call_action(self, hand: "Hand", street: str, player: str, action: re.Match[str]) -> None:
        """Handle call actions for a player on a given street.

        This method processes call actions, extracting the bet amount and updating the Hand object
        with the call information for the specified player and street.

        Args:
            hand: The Hand object to update with call action information.
            street: The street name where the call occurs.
            player: The player making the call.
            action: The regex match object representing the call action.
        """
        if not action.group("BET"):
            log.error("Amount not found in Call %s", hand.handid)
            raise FpdbParseError
        hand.addCall(
            street,
            player,
            self.clearMoneyString(action.group("BET")),
        )

    def _handle_raise_action(self, hand: "Hand", street: str, player: str, action: re.Match[str]) -> None:
        """Handle raise actions for a player on a given street.

        This method processes raise actions, extracting the raise-to or bet amount and updating the Hand object
        with the raise information for the specified player and street.

        Args:
            hand: The Hand object to update with raise action information.
            street: The street name where the raise occurs.
            player: The player making the raise.
            action: The regex match object representing the raise action.
        """
        if action.group("BETTO"):
            bet = self.clearMoneyString(action.group("BETTO"))
        elif action.group("BET"):
            bet = self.clearMoneyString(action.group("BET"))
        else:
            log.error("Amount not found in Raise %s", hand.handid)
            raise FpdbParseError
        hand.addRaiseTo(street, player, bet)

    def _handle_bet_action(self, hand: "Hand", street: str, player: str, action: re.Match[str]) -> None:
        """Handle bet actions for a player on a given street.

        This method processes bet actions, extracting the bet amount and updating the Hand object
        with the bet information for the specified player and street.

        Args:
            hand: The Hand object to update with bet action information.
            street: The street name where the bet occurs.
            player: The player making the bet.
            action: The regex match object representing the bet action.
        """
        if not action.group("BET"):
            log.error("Amount not found in Bet %s", hand.handid)
            raise FpdbParseError
        hand.addBet(
            street,
            player,
            self.clearMoneyString(action.group("BET")),
        )

    def _handle_allin_action(self, hand: "Hand", street: str, player: str, action: re.Match[str]) -> None:
        """Handle all-in actions for a player on a given street.

        This method processes all-in actions, extracting the bet amount and updating the Hand object
        with the all-in information for the specified player and street.

        Args:
            hand: The Hand object to update with all-in action information.
            street: The street name where the all-in occurs.
            player: The player making the all-in.
            action: The regex match object representing the all-in action.
        """
        if not action.group("BET"):
            log.error(
                "BovadaToFpdb.readAction: Amount not found in All-in %s",
                hand.handid,
            )
            raise FpdbParseError
        hand.addAllIn(
            street,
            player,
            self.clearMoneyString(action.group("BET")),
        )
        self.allInBlind(hand, street, action)

    def allInBlind(self, hand: "Hand", street: str, action: re.Match[str]) -> None:
        """Handle all-in blind situations for a player on a given street.

        This method checks if a player is all-in during the PREFLOP or DEAL street and updates the Hand object
        to indicate uncalled bets and the all-in blind status if appropriate.

        Args:
            hand: The Hand object to update with all-in blind information.
            street: The street name where the all-in blind may occur.
            action: The regex match object representing the action.
        """
        if street in {"PREFLOP", "DEAL"}:
            player = self.playerSeatFromPosition(
                "BovadaToFpdb.allInBlind",
                hand.handid,
                action.group("PNAME"),
            )
            if hand.stacks[player] == 0 and not self.re_return_bet.search(hand.handText):
                hand.setUncalledBets(True)
                hand.allInBlind = True

    def readShowdownActions(self, hand: "Hand") -> None:
        """Read and assign showdown card information for the hand.

        This method processes the hand text to extract and assign cards shown at showdown,
        updating the Hand object with the shown cards for each player.

        Args:
            hand: The Hand object to update with showdown card information.
        """
        # TODO(fpdb): pick up mucks also??
        if hand.gametype["base"] in ("hold"):
            for shows in self.re_showdown_action.finditer(hand.handText):
                cards = shows.group("CARDS").split(" ")
                player = self.playerSeatFromPosition(
                    "BovadaToFpdb.readShowdownActions",
                    hand.handid,
                    shows.group("PNAME"),
                )
                hand.addShownCards(cards, player)

    def readCollectPot(self, hand: "Hand") -> None:
        """Read and assign collected pot information for the hand.

        This method processes the hand text to extract and assign the amount collected by each player,
        updating the Hand object with the collected pot values.

        Args:
            hand: The Hand object to update with collected pot information.
        """
        re_collect_pot = self.re_collect_pot2 if self.re_collect_pot2.search(hand.handText) else self.re_collect_pot1
        for m in re_collect_pot.finditer(
            hand.handText.replace(" [ME]", "") if hand.version == "MVS" else hand.handText,
        ):  # [ME]
            collect, pot = m.groupdict(), 0
            if "POT1" in collect and collect["POT1"] is not None:
                pot += Decimal(self.clearMoneyString(collect["POT1"]))
            if "POT2" in collect and collect["POT2"] is not None:
                pot += Decimal(self.clearMoneyString(collect["POT2"]))
            if pot > 0:
                player = self.playerSeatFromPosition(
                    "BovadaToFpdb.readCollectPot",
                    hand.handid,
                    collect["PNAME"],
                )
                hand.addCollectPot(player=player, pot=str(pot))

    def readShownCards(self, hand: "Hand") -> None:
        """Read and assign shown card information for the hand.

        This method processes the hand text to extract and assign cards that were shown by players,
        updating the Hand object with the shown cards for each player.

        Args:
            hand: The Hand object to update with shown card information.
        """

    def readTourneyResults(self, hand: "Hand") -> None:
        """Read and assign tournament results for the hand.

        This method processes the hand text to extract and assign knockout (KO) counts for each player,
        updating the Hand object with the number of knockouts achieved.

        Args:
            hand: The Hand object to update with tournament result information.
        """
        for a in self.re_bounty.finditer(hand.handText):
            player = self.playerSeatFromPosition(
                "BovadaToFpdb.readCollectPot",
                hand.handid,
                a.group("PNAME"),
            )
            if player not in hand.koCounts:
                hand.koCounts[player] = 0
            hand.koCounts[player] += 1

    def readOther(self, hand: "Hand") -> None:
        """Read and assign additional hand information such as rake and pot totals.

        This method processes the hand text to extract rake and pot information, updating the Hand object
        with these values or marking the hand as Zone Poker if only a summary is found.

        Args:
            hand: The Hand object to update with additional hand information.
        """
        # Check if this is Zone Poker based on game type fast flag
        if hasattr(hand, 'gametype') and hand.gametype.get('fast'):
            hand.isZonePoker = True
        else:
            hand.isZonePoker = False
            
        if m := self.re_rake.search(hand.handText):
            rake_amount = self.clearMoneyString(m.group("RAKE"))
            pot_amount = self.clearMoneyString(m.group("POT"))
            hand.rake = Decimal(rake_amount)
            hand.totalpot = Decimal(pot_amount)
            log.debug("Bovada rake found in history: rake=%s, pot=%s", hand.rake, hand.totalpot)
        elif m := self.re_pot_no_rake.search(hand.handText):
            pot_amount = self.clearMoneyString(m.group("POT"))
            hand.totalpot = Decimal(pot_amount)
            log.debug("Bovada pot found without rake: pot=%s", hand.totalpot)
        elif self.re_summary.search(hand.handText):
            log.warning(
                "Bovada hand %s has Summary section but no pot information - may be incomplete",
                hand.handid,
            )
            hand.isZonePoker = True

    def getRake(self, hand: "Hand") -> None:
        """Read and assign rake information for the hand.

        This method checks if the rake has already been set, handles special cases for Zone Poker hands,
        and otherwise delegates to the parent method to calculate the rake.

        Args:
            hand: The Hand object to update with rake information.
        """
        # If rake was already set by readOther, don't recalculate
        if hand.rake is not None:
            log.debug("Bovada rake already set: %s", hand.rake)
            return

        # Special handling for Zone Poker hands with empty Summary sections
        if hasattr(hand, "isZonePoker") and hand.isZonePoker:
            log.debug("Zone Poker hand %s - using collected amount as pot total", hand.handid)
            # For Zone Poker hands, the collected amount is often the actual pot total
            # This is a workaround for hands with missing Summary information
            if hand.totalcollected is not None:
                # Set totalpot to collected amount (rake is already deducted)
                hand.totalpot = hand.totalcollected
                hand.rake = Decimal("0.00")  # Rake already deducted from collected amount
                log.debug("Zone Poker hand %s: pot=%s, rake=%s", hand.handid, hand.totalpot, hand.rake)
                return

        # Otherwise, use parent method to calculate
        super().getRake(hand)
