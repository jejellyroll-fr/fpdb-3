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
log = get_logger("parser")


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
        r"Dealer : Set dealer\/Bring in spot \[(?P<BUTTON>\d+)\]",
        re.MULTILINE,
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
        r"(RING|ZONE)\s-\s(?P<CURRENCY>{LS}|)?(?P<SB>[{NUM}]+)-({LS})?(?P<BB>[{NUM}]+)".format(**substitutions),
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
        """Compile player-specific regex patterns."""
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
        """Read summary information from tournament files."""
        log.info("enter method readSummaryInfo.")
        log.debug("Method readSummaryInfo non implemented.")
        return True

    def readSupportedGames(self) -> list[list[str]]:
        """Return list of supported game types."""
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
        """Parse hand header information."""
        gametype = self.determineGameType(hand_text)
        if gametype["type"] == "tour":
            handlist = re.split(self.re_split_hands, whole_file)
            result = re.findall(self.re_player_seat, handlist[0])
            gametype["maxSeats"] = len(result)
        return gametype

    def determineGameType(self, hand_text: str) -> dict[str, str]:
        """Determine game type information from hand text."""
        self._validateHandText(hand_text)
        mg = self._extractGameInfo(hand_text)
        info = self._buildGameTypeInfo(mg)
        self._adjustFixedLimitBlinds(info, mg, hand_text)
        return info

    def _validateHandText(self, hand_text: str) -> None:
        """Validate hand text completeness."""
        m = self.re_game_info.search(hand_text)
        if not m:
            tmp = hand_text[0:200]
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

    def _extractGameInfo(self, hand_text: str) -> dict[str, str]:
        """Extract game information from hand text."""
        m = self.re_game_info.search(hand_text)
        mg = m.groupdict()
        m = self.re_stakes.search(self.in_path)
        if m:
            mg.update(m.groupdict())
        return mg

    def _buildGameTypeInfo(self, mg: dict[str, str]) -> dict[str, str]:
        """Build game type information from matches."""
        info = {}

        # Set limit type
        if "LIMIT" in mg:
            info["limitType"] = "nl" if not mg["LIMIT"] else self.limits[mg["LIMIT"]]

        # Set game base and category
        if "GAME" in mg:
            (info["base"], info["category"]) = self.games[mg["GAME"]]

        # Set blinds
        if "SB" in mg:
            info["sb"] = self.clearMoneyString(mg["SB"])
        if "BB" in mg:
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

        return info

    def _adjustFixedLimitBlinds(self, info: dict[str, str], mg: dict[str, str], hand_text: str) -> None:
        """Adjust blinds for fixed limit games."""
        if info["limitType"] == "fl" and info["bb"] is not None:
            if info["type"] == "ring":
                try:
                    info["sb"] = self.lim_blinds[info["bb"]][0]
                    info["bb"] = self.lim_blinds[info["bb"]][1]
                except KeyError:
                    tmp = hand_text[0:200]
                    log.exception("lim_blinds has no lookup for '%s' - '%s'", mg["BB"], tmp)
                    raise FpdbParseError from None
            else:
                info["sb"] = str((Decimal(info["sb"]) / 2).quantize(Decimal("0.01")))
                info["bb"] = str(Decimal(info["sb"]).quantize(Decimal("0.01")))

    def readHandInfo(self, hand: "Hand") -> None:
        """Read basic hand information."""
        info = self._extractHandInfo(hand)
        self._setHandSpeed(hand)
        self._processHandInfoKeys(hand, info)

    def _extractHandInfo(self, hand: "Hand") -> dict[str, str]:
        """Extract hand information from text and path."""
        info = {}
        m = self.re_game_info.search(hand.handText)
        if m is None:
            tmp = hand.handText[0:200]
            log.error("readHandInfo not found: '%s'", tmp)
            raise FpdbParseError

        info.update(m.groupdict())
        m = self.re_buyin.search(self.in_path)
        if m:
            info.update(m.groupdict())
        hand.allInBlind = False
        m2 = self.re_knockout.search(self.in_path)
        if m2:
            info.update(m2.groupdict())
        return info

    def _setHandSpeed(self, hand: "Hand") -> None:
        """Set hand speed based on path."""
        if "Hyper Turbo" in self.in_path:
            hand.speed = "Hyper"
        elif "Turbo" in self.in_path:
            hand.speed = "Turbo"

    def _processHandInfoKeys(self, hand: "Hand", info: dict[str, str]) -> None:
        """Process hand info keys and set hand attributes."""
        for key in info:
            if key == "DATETIME":
                m1 = self.re_date_time.finditer(info[key])
                datetimestr = "2000/01/01 00:00:00"  # default used if time not found
                for a in m1:
                    datetimestr = "{}/{}/{} {}:{}:{}".format(
                        a.group("Y"),
                        a.group("M"),
                        a.group("D"),
                        a.group("H"),
                        a.group("MIN"),
                        a.group("S"),
                    )
                    # print "   tz = ", tz, " datetime =", datetimestr
                hand.startTime = datetime.datetime.strptime(
                    datetimestr,
                    "%Y/%m/%d %H:%M:%S",
                )  # also timezone at end, e.g. " ET"
                hand.startTime = HandHistoryConverter.changeTimezone(
                    hand.startTime,
                    "ET",
                    "UTC",
                )
            if key == "HID":
                hand.handid = info[key]
            if key == "TOURNO":
                hand.tourNo = info[key]
            if key == "BUYIN" and info["TOURNO"] is not None:
                if info[key] == "Freeroll":
                    hand.buyin = 0
                    hand.fee = 0
                    hand.buyinCurrency = "FREE"
                else:
                    if info[key].find("$") != -1:
                        hand.buyinCurrency = "USD"
                    elif re.match("^[0-9+]*$", info[key]):
                        hand.buyinCurrency = "play"
                    else:
                        # TODO(fpdb): handle other currencies, play money
                        log.error(
                            "Failed to detect currency. Hand ID: %s: '%s'",
                            hand.handid,
                            info[key],
                        )
                        raise FpdbParseError

                    if info.get("BOUNTY") is not None:
                        info["BOUNTY"] = self.clearMoneyString(
                            info["BOUNTY"].strip("$"),
                        )  # Strip here where it isn't 'None'
                        hand.koBounty = int(100 * Decimal(info["BOUNTY"]))
                        hand.isKO = True
                    else:
                        hand.isKO = False

                    info["BIAMT"] = self.clearMoneyString(info["BIAMT"].strip("$"))

                    if info["BIRAKE"]:
                        info["BIRAKE"] = self.clearMoneyString(
                            info["BIRAKE"].strip("$"),
                        )
                    else:
                        info["BIRAKE"] = "0"

                    if info["TICKET"] is None:
                        hand.buyin = int(100 * Decimal(info["BIAMT"]))
                        hand.fee = int(100 * Decimal(info["BIRAKE"]))
                    else:
                        hand.buyin = 0
                        hand.fee = 0
            if key == "TABLE":
                if info.get("TABLENO"):
                    hand.tablename = info.get("TABLENO")
                elif info["ZONE"] and "Zone" in info["ZONE"]:
                    hand.tablename = info["ZONE"] + " " + info[key]
                else:
                    hand.tablename = info[key]
            if key == "MAX" and info[key] is not None:
                hand.maxseats = int(info[key])
            if key == "HU" and info[key] is not None:
                hand.maxseats = 2
            if key == "VERSION":
                hand.version = info[key]

        if not hand.maxseats:
            hand.maxseats = 9

        if not hand.version:
            hand.version = "LEGACY"

    def readButton(self, hand: "Hand") -> None:
        """Read button position information."""
        m = self.re_button.search(hand.handText)
        if m:
            hand.buttonpos = int(m.group("BUTTON"))

    def readPlayerStacks(self, hand: "Hand") -> None:
        """Read player stack information."""
        self.playersMap, seat_no = {}, 1
        if hand.gametype["base"] in ("stud"):
            m = self.re_player_info_stud.finditer(hand.handText)
        else:
            m = self.re_player_info.finditer(hand.handText)
        for a in m:
            if (
                re.search(
                    r"{} (\s?\[ME\]\s)?: Card dealt to a spot".format(re.escape(a.group("PNAME"))),
                    hand.handText,
                )
                or hand.version == "MVS"
            ):
                if not hand.buttonpos and a.group("PNAME") == "Dealer":
                    hand.buttonpos = int(a.group("SEAT"))
                if a.group("HERO"):
                    self.playersMap[a.group("PNAME")] = "Hero"
                else:
                    self.playersMap[a.group("PNAME")] = "Seat {}".format(a.group("SEAT"))
                hand.addPlayer(
                    seat_no,
                    self.playersMap[a.group("PNAME")],
                    self.clearMoneyString(a.group("CASH")),
                )
            seat_no += 1
        if len(hand.players) == 0:
            tmp = hand.handText[0:200]
            log.error("readPlayerStacks failed: '%s'", tmp)
            raise FpdbParseError
        max_full_ring_players = 10
        if len(hand.players) == max_full_ring_players:
            hand.maxseats = max_full_ring_players

    def playerSeatFromPosition(self, source: str, handid: str, position: str) -> str:
        """Get player seat from position."""
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

    def markStreets(self, hand: "Hand") -> None:
        """Mark street positions in hand text."""
        # PREFLOP = ** Dealing down cards **
        # This re fails if,  say, river is missing; then we don't get the ** that starts the river.
        if hand.gametype["base"] == "hold":
            street, firststreet = "PREFLOP", "PREFLOP"
        else:
            street, firststreet = "THIRD", "THIRD"
        m = self.re_action.finditer(self.re_hole_third.split(hand.handText)[0])
        allinblind = 0
        for action in m:
            if action.group("ATYPE") == " All-in":
                allinblind += 1
        m = self.re_action.finditer(self.re_hole_third.split(hand.handText)[-1])
        dealt_in = len(hand.players) - allinblind
        streetactions, streetno, players, contenders, bets, acts = (
            0,
            1,
            dealt_in,
            0,
            dealt_in,
            None,
        )
        for action in m:
            if action.groupdict() != acts or streetactions == 0:
                acts = action.groupdict()
                # DEBUG: street, acts['PNAME'], acts['ATYPE'], action.group('BET'), streetactions, players, contenders
                if action.group("ATYPE") == " Fold":
                    contenders -= 1
                elif action.group("ATYPE") in (" Raises", " raises"):
                    if streetno == 1:
                        bets = 1
                    streetactions, players = 0, contenders
                elif action.group("ATYPE") in (" Bets", " bets", " Double bets"):
                    streetactions, players, bets = 0, contenders, 1
                elif action.group("ATYPE") in (
                    " All-in(raise)",
                    "All-in(raise-timeout)",
                ):
                    streetactions, players = 0, contenders
                    contenders -= 1
                elif action.group("ATYPE") == " All-in":
                    if bets == 0 and streetno > 1:
                        streetactions, players, bets = 0, contenders, 1
                    contenders -= 1
                if action.group("ATYPE") != " Card dealt to a spot" and (
                    action.group("ATYPE") != " Big blind/Bring in" or hand.gametype["base"] == "stud"
                ):
                    streetactions += 1
                hand.streets[street] += action.group("ACTION") + "\n"
                # print street, action.group('PNAME'), action.group('ATYPE'), streetactions, players, contenders
                if streetactions == players:
                    streetno += 1
                    if streetno < len(hand.actionStreets):
                        street = hand.actionStreets[streetno]
                    streetactions, players, bets = 0, contenders, 0

        if not hand.streets.get(firststreet):
            hand.streets[firststreet] = hand.handText
        if hand.gametype["base"] == "hold":
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

    def readCommunityCards(
        self,
        hand: "Hand",
        street: str,
    ) -> None:
        """Read community cards for a street."""
        if hand.gametype["fast"]:
            m = self.re_board2[street].search(hand.handText)
            if m and m.group("CARDS"):
                hand.setCommunityCards(street, m.group("CARDS").split(" "))
        elif street in (
            "FLOP",
            "TURN",
            "RIVER",
        ):  # a list of streets which get dealt community cards (i.e. all but PREFLOP)
            m = self.re_board1.search(hand.handText)
            if m and m.group(street):
                cards = m.group(street).split(" ")
                hand.setCommunityCards(street, cards)

    def readAntes(self, hand: "Hand") -> None:
        """Read ante information."""
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
        """Read bring-in information for stud games."""
        m = self.re_bring_in.search(hand.handText, re.DOTALL)
        if m:
            player = self.playerSeatFromPosition(
                "BovadaToFpdb.readBringIn",
                hand.handid,
                m.group("PNAME"),
            )
            hand.addBringIn(player, self.clearMoneyString(m.group("BRINGIN")))

        if hand.gametype["sb"] is None and hand.gametype["bb"] is None:
            hand.gametype["sb"] = "1"
            hand.gametype["bb"] = "2"

    def readBlinds(self, hand: "Hand") -> None:
        """Read blind information."""
        # sb, bb,
        heads_up_players = 2
        acts, postsb, postbb, both = None, None, None, None  # , None, None
        if not self.re_return_bet.search(hand.handText):
            hand.setUncalledBets(True)
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
            self.allInBlind(hand, "PREFLOP", a, "small blind")
        for a in self.re_post_bb.finditer(hand.handText):
            if postbb != a.groupdict():
                postbb = a.groupdict()
                player = self.playerSeatFromPosition(
                    "BovadaToFpdb.readBlinds.postBB",
                    hand.handid,
                    "Big Blind",
                )
                hand.addBlind(player, "big blind", self.clearMoneyString(postbb["BB"]))
                self.allInBlind(hand, "PREFLOP", a, "big blind")
                if not hand.gametype["bb"]:
                    hand.gametype["bb"] = self.clearMoneyString(postbb["BB"])
                if not hand.gametype["currency"]:
                    if postbb["CURRENCY"].find("$") != -1:
                        hand.gametype["currency"] = "USD"
                    elif re.match("^[0-9+]*$", postbb["CURRENCY"]):
                        hand.gametype["currency"] = "play"
        for a in self.re_action.finditer(self.re_hole_third.split(hand.handText)[0]):
            if acts != a.groupdict():
                acts = a.groupdict()
                if acts["ATYPE"] == " All-in":
                    re_ante_plyr = re.compile(
                        r"^"
                        + re.escape(acts["PNAME"])
                        + r" (\s?\[ME\]\s)?: Ante chip {CUR}(?P<ANTE>[{NUM}]+)".format(**self.substitutions),
                        re.MULTILINE,
                    )
                    m = self.re_antes.search(hand.handText)
                    m1 = re_ante_plyr.search(hand.handText)
                    if not m or m1:
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
                            self.allInBlind(hand, "PREFLOP", a, "big blind")
                        elif acts["PNAME"] == "Small Blind" or (
                    acts["PNAME"] == "Dealer" and len(hand.players) == heads_up_players  # Head-to-head
                ):
                            hand.addBlind(
                                player,
                                "small blind",
                                self.clearMoneyString(acts["BET"]),
                            )
                            self.allInBlind(hand, "PREFLOP", a, "small blind")
                    elif m:
                        player = self.playerSeatFromPosition(
                            "BovadaToFpdb.readAntes",
                            hand.handid,
                            acts["PNAME"],
                        )
                        hand.addAnte(player, self.clearMoneyString(acts["BET"]))
                        self.allInBlind(hand, "PREFLOP", a, "antes")
        self.fixBlinds(hand)
        for a in self.re_post_both.finditer(hand.handText):
            if both != a.groupdict():
                both = a.groupdict()
                player = self.playerSeatFromPosition(
                    "BovadaToFpdb.readBlinds.postBoth",
                    hand.handid,
                    both["PNAME"],
                )
                hand.addBlind(player, "both", self.clearMoneyString(both["SBBB"]))
                self.allInBlind(hand, "PREFLOP", a, "both")

    def fixBlinds(self, hand: "Hand") -> None:
        """Fix blind information for the hand."""
        if hand.gametype["sb"] is None and hand.gametype["bb"] is not None:
            big_blind = str(Decimal(hand.gametype["bb"]) * 2)
            if self.lim_blinds.get(big_blind) is not None:
                hand.gametype["sb"] = self.lim_blinds.get(big_blind)[0]
        elif hand.gametype["bb"] is None and hand.gametype["sb"] is not None:
            for _k, v in list(self.lim_blinds.items()):
                if hand.gametype["sb"] == v[0]:
                    hand.gametype["bb"] = v[1]

        # Special handling for problematic hands - use filename to determine blinds
        if hand.gametype["sb"] is None or hand.gametype["bb"] is None:
            # Try to extract blinds from filename
            filename_blinds = self._extractBlindsFromFilename()
            if filename_blinds:
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
        """Extract blinds from filename for problematic hands."""
        if not hasattr(self, "in_path") or not self.in_path:
            return None

        from pathlib import Path

        filename = Path(self.in_path).name

        # Pattern to match blinds in filename like "$8-$16" or "$30-$60"
        import re

        pattern = r"\$(\d+(?:\.\d+)?)-\$(\d+(?:\.\d+)?)"
        match = re.search(pattern, filename)

        if match:
            # Extract the limit structure from filename
            # For "$8-$16", the key is "16" (the higher value)
            # For "$30-$60", the key is "60" (the higher value)
            limit_key = match.group(2)

            # Look up in lim_blinds dictionary
            if limit_key in self.lim_blinds:
                return self.lim_blinds[limit_key]  # Return (small_blind, big_blind)

            # Also try with ".00" suffix for exact match
            limit_key_with_decimals = limit_key + ".00"
            if limit_key_with_decimals in self.lim_blinds:
                return self.lim_blinds[limit_key_with_decimals]

        return None

    def readSTP(self, hand: "Hand") -> None:
        """Read Splash the Pot information from hand text."""

    def readHoleCards(self, hand: "Hand") -> None:
        """Read hole cards information."""
        #    streets PREFLOP, PREDRAW, and THIRD are special cases beacause
        #    we need to grab hero's cards
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

        for street, text in list(hand.streets.items()):
            if not text or street in ("PREFLOP", "DEAL"):
                continue  # already done these
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

                    if street == "THIRD" and found.group("HERO"):  # hero in stud game
                        hand.hero = "Hero"
                        hand.dealt.add(player)  # need this for stud??
                        min_stud_cards = 3
                        if len(newcards) >= min_stud_cards:
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
                                closed=newcards,
                                open=[],
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

    def readAction(self, hand: "Hand", street: str) -> None:
        """Read action information for a street."""
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
                # DEBUG: street, acts['PNAME'], player, acts['ATYPE'], action.group('BET')
                if (
                    action.group("ATYPE")
                    not in (
                        " Checks",
                        " Fold",
                        " Card dealt to a spot",
                        " Big blind/Bring in",
                    )
                    and not hand.allInBlind
                ):
                    hand.setUncalledBets(False)
                if action.group("ATYPE") == " Fold":
                    hand.addFold(street, player)
                elif action.group("ATYPE") == " Checks":
                    hand.addCheck(street, player)
                elif action.group("ATYPE") == " Calls" or action.group("ATYPE") == " Call":
                    if not action.group("BET"):
                        log.error("Amount not found in Call %s", hand.handid)
                        raise FpdbParseError
                    hand.addCall(
                        street,
                        player,
                        self.clearMoneyString(action.group("BET")),
                    )
                elif action.group("ATYPE") in (
                    " Raises",
                    " raises",
                    " All-in(raise)",
                    " All-in(raise-timeout)",
                ):
                    if action.group("BETTO"):
                        bet = self.clearMoneyString(action.group("BETTO"))
                    elif action.group("BET"):
                        bet = self.clearMoneyString(action.group("BET"))
                    else:
                        log.error("Amount not found in Raise %s", hand.handid)
                        raise FpdbParseError
                    hand.addRaiseTo(street, player, bet)
                elif action.group("ATYPE") in (" Bets", " bets", " Double bets"):
                    if not action.group("BET"):
                        log.error("Amount not found in Bet %s", hand.handid)
                        raise FpdbParseError
                    hand.addBet(
                        street,
                        player,
                        self.clearMoneyString(action.group("BET")),
                    )
                elif action.group("ATYPE") == " All-in":
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
                    self.allInBlind(hand, street, action, action.group("ATYPE"))
                elif action.group("ATYPE") == " Bring_in chip" or action.group("ATYPE") in (
                    " Card dealt to a spot",
                    " Big blind/Bring in",
                ):
                    pass
                else:
                    log.debug(
                        "Unimplemented readAction: '%s' '%s'",
                        action.group("PNAME"),
                        action.group("ATYPE"),
                    )

    def allInBlind(self, hand: "Hand", street: str, action: re.Match[str], actiontype: str) -> None:  # noqa: ARG002
        """Check if hand is all-in on blinds."""
        if street in ("PREFLOP", "DEAL"):
            player = self.playerSeatFromPosition(
                "BovadaToFpdb.allInBlind",
                hand.handid,
                action.group("PNAME"),
            )
            if hand.stacks[player] == 0 and not self.re_return_bet.search(hand.handText):
                hand.setUncalledBets(True)
                hand.allInBlind = True

    def readShowdownActions(self, hand: "Hand") -> None:
        """Read showdown actions."""
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
        """Read pot collection information."""
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
        """Read shown cards information."""

    def readTourneyResults(self, hand: "Hand") -> None:
        """Read tournament results information."""
        """Reads knockout bounties and add them to the koCounts dict."""
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
        """Read other information from hand text."""
        # Check if rake is explicitly provided in the hand history
        m = self.re_rake.search(hand.handText)
        if m:
            # When rake is explicitly provided, use it directly
            rake_amount = self.clearMoneyString(m.group("RAKE"))
            pot_amount = self.clearMoneyString(m.group("POT"))
            hand.rake = Decimal(rake_amount)
            # Set totalpot to the pot amount from summary (includes rake)
            hand.totalpot = Decimal(pot_amount)
            log.debug("Bovada rake found in history: rake=%s, pot=%s", hand.rake, hand.totalpot)
        else:
            # Check for pot total without explicit rake
            m = self.re_pot_no_rake.search(hand.handText)
            if m:
                pot_amount = self.clearMoneyString(m.group("POT"))
                hand.totalpot = Decimal(pot_amount)
                # Let getRake() calculate the rake normally
                log.debug("Bovada pot found without rake: pot=%s", hand.totalpot)
            elif self.re_summary.search(hand.handText):
                log.warning(
                    "Bovada hand %s has Summary section but no pot information - may be incomplete",
                    hand.handid,
                )
                # For Zone Poker hands with empty Summary, we need to let the normal
                # pot calculation work, but be more lenient with rake calculation
                # Mark this as a Zone Poker hand for special handling
                hand.isZonePoker = True

    def getRake(self, hand: "Hand") -> None:
        """Calculate rake for Bovada hands."""
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
