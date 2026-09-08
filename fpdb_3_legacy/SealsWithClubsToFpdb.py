#!/usr/bin/env python
from __future__ import annotations

#
#    Copyright 2008-2013, Carl Gherardi
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
# import L10n
# _ = L10n.get_translation()
import datetime
import re
from decimal import Decimal
from typing import TYPE_CHECKING

from fpdb_3_legacy.HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from fpdb_3_legacy.loggingFpdb import get_logger

if TYPE_CHECKING:
    from fpdb_3_legacy.Hand import Hand
# SealsWithClubs HH Format
log = get_logger("seals_with_clubs_parser")


class SealsWithClubs(HandHistoryConverter):
    # Class Variables

    sitename = "SealsWithClubs"
    filetype = "text"
    codepage = ("utf8", "cp1252")
    siteId = 23  # Needs to match id entry in Sites database
    compiledPlayers: set[str] = set()
    substitutions = {
        "PLYR": r"(?P<PNAME>\w+)",
        "BRKTS": r"(\(button\) |\(small blind\) |\(big blind\) |\(button\) \(small blind\) |\(button\) \(big blind\) )?",
    }

    limits = {
        "NL": "nl",
        "No Limit": "nl",
        "PL": "pl",
        "Limit": "fl",
        "Fixed Limit": "fl",
        "Pot Limit": "pl",
    }
    games = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi-Lo": ("hold", "omahahilo"),
        "Short Deck Hold'em": ("hold", "6_holdem"),
        "Omaha 5 Cards": ("hold", "5_omahahi"),
    }

    # Static regexes
    re_GameInfo = re.compile(
        r"""SwCPoker\sHand\s*\#(?P<HID>\d+):\s((Tournament|Cashgame|sitngo)\s\(((?P<TABLE2>.*?))\)\#(?P<TOURNO>\d+),\s(?P<BUYIN>(?P<BIAMT>\d+(\.\d+)?))\+(?P<BIRAKE>\d+(\.\d+)?)\s|\s)(?P<GAME>(Hold\'em|Omaha|Omaha\s5\sCards|Short\sDeck\sHold\'em))\s(?P<LIMIT>(NL|Fixed\sLimit|PL|Limit|Pot\sLimit|No\sLimit))\s((-\sLevel\s\w+\s)|)\((?P<SB>\d+(\.\d+)?(\,\d+)?)/(?P<BB>\d+(\.\d+)?(\,\d+)?)\)\s-\s(?P<DATETIME>.*)""",
        re.VERBOSE,
    )

    re_PlayerInfo = re.compile(
        r"""^Seat\s+(?P<SEAT>\d+):\s+(?P<PNAME>\w+)\s+\((?P<CASH>\d{1,3}(,\d{3})*(\.\d+)?)\sin\schips\)""",
        re.MULTILINE | re.VERBOSE,
    )

    re_HandInfo = re.compile(
        r"""^Table\s'(?P<TABLE>.*?)'\(\d+\)\s(?P<MAX>\d+)-max\s(?:\(Real Money\)\s)?Seat\s\#\d+\sis\sthe\sbutton""",
        re.MULTILINE,
    )

    re_identify = re.compile(r"SwCPoker\sHand\s|^Site:\sSeals\sWith\sClubs", re.MULTILINE)
    re_SplitHands = re.compile("(?:\\s?\n){2,}")
    re_ButtonName = re.compile(
        r"""^(?P<BUTTONNAME>.*) has the dealer button""",
        re.MULTILINE,
    )
    re_ButtonPos = re.compile(
        r"""Seat\s+\#(?P<BUTTON>\d+)\sis\sthe\sbutton""",
        re.MULTILINE,
    )
    re_Board = re.compile(r"\[(?P<CARDS>.+)\]")
    re_DateTime = re.compile(
        r"""(?P<Y>\d{4})[-/](?P<M>\d{2})[-/](?P<D>\d{2})[\-\s]+(?P<H>\d+):(?P<MIN>\d+):(?P<S>\d+)""",
        re.MULTILINE,
    )

    # These used to be compiled per player, but regression tests say
    # we don't have to, and it makes life faster.
    re_PostSB = re.compile(
        r"^{PLYR}: posts small blind (?P<SB>[.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_PostBB = re.compile(
        r"^{PLYR}: posts big blind (?P<BB>[.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_Antes = re.compile(
        r"^{PLYR}: posts the ante (?P<ANTE>[.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_PostBoth = re.compile(
        r"^{PLYR}: posts small \& big blind (?P<SBBB>[.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_HeroCards = re.compile(
        r"^Dealt to {PLYR}(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(**substitutions),
        re.MULTILINE,
    )
    re_Action = re.compile(
        r"""^{PLYR}:(?P<ATYPE>\sbets|\schecks|\sraises|\scalls|\sfolds|\sdiscards|\sstands\spat)(?:\s(?P<BET>\d{{1,3}}(,\d{{3}})*(\.\d+)?))?(?:\sto\s(?P<POT>\d{{1,3}}(,\d{{3}})*(\.\d+)?))?(?:\sand\sis\sall-in)?.*?$""".format(
            **substitutions
        ),
        re.MULTILINE | re.VERBOSE,
    )

    re_ShowdownAction = re.compile(
        r"^(?P<PNAME>\w+): (shows \[(?P<CARDS>.*)\]\s\((?P<FHAND>.*?)\)|doesn't show hand|mucks hand)",
        re.MULTILINE,
    )
    re_CollectPot = re.compile(
        r"^Seat (?P<SEAT>[0-9]+): {PLYR} (({BRKTS}(((((?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]( and (lost|(won|collected) \((?P<POT>[.,\d]+)\)) with (?P<STRING>.+?)(\s\sand\s(won\s\([.,\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?$)|collected\s\((?P<POT2>[.,\d]+)\)))|folded ((on the (Flop|Turn|River))|before Flop)))|folded before Flop \(didn't bet\))".format(
            **substitutions
        ),
        re.MULTILINE,
    )
    re_Cancelled = re.compile(r"Hand\scancelled", re.MULTILINE)
    re_Uncalled = re.compile(
        r"Uncalled bet \((?P<BET>[,.\d]+)\) returned to {PLYR}".format(**substitutions),
        re.MULTILINE,
    )
    re_Flop = re.compile(r"\*\*\* FLOP \*\*\*")
    re_Turn = re.compile(r"\*\*\* TURN \*\*\*")
    re_River = re.compile(r"\*\*\* RIVER \*\*\*")

    #: How a client names the two boards of a double-board hand. A bomb pot at a
    #: "Double Board" table deals two runouts and splits the pot between them, so
    #: the header appears once per board per street. Both spellings this codebase
    #: already parses elsewhere are accepted -- "FIRST/SECOND" (PokerStarsToFpdb,
    #: GGPokerToFpdb) and a trailing run number (WinningToFpdb) -- because a hand
    #: that names its boards in neither is not treated as double-board at all.
    DOUBLE_BOARD_NAMING = (
        ("FIRST {street}", "SECOND {street}"),
        ("{street} 1", "{street} 2"),
    )
    BOARD_STREETS = ("FLOP", "TURN", "RIVER")
    re_rake = re.compile(
        "Total pot (?P<TOTALPOT>\\d{1,3}(,\\d{3})*(\\.\\d+)?)\\s\\|\\sRake\\s(?P<RAKE>\\d{1,3}(,\\d{3})*(\\.\\d+)?)",
        re.MULTILINE,
    )
    re_Mucked = re.compile("^{PLYR}: mucks hand".format(**substitutions), re.MULTILINE)

    # ------------------------------------------------------------------
    # Legacy "Seals With Clubs" 2013 text format (pre-SwCPoker rewrite).
    # Distinct grammar: a "Game:/Site:/Table:" header, two-star street
    # markers (** Flop **), and colon-less actions ("Player calls 2").
    # Detected by the absence of the modern "SwCPoker Hand" marker.
    # ------------------------------------------------------------------
    re_NewFormat = re.compile(r"SwCPoker\sHand\s")
    re_OldGameInfo = re.compile(
        r"""^Hand\s\#(?P<HID>\d+-\d+)\s-\s(?P<DATETIME>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s*\n
            Game:\s(?P<LIMIT>No\sLimit|Pot\sLimit|Fixed\sLimit|NL|PL|FL|Limit)\s
            (?P<GAME>Hold'em|Omaha\sHi-Lo|Omaha)\s
            \([\d\s\-]+\)\s-\s(?:Blinds|Stakes)\s(?P<SB>[\d.]+)/(?P<BB>[\d.]+)""",
        re.MULTILINE | re.VERBOSE,
    )
    re_OldTable = re.compile(r"^Table:\s(?P<TABLE>.+?)\s*$", re.MULTILINE)
    re_OldMax = re.compile(r"\b(?:(?P<MAX>\d+)max|(?P<HU>HU))\b")
    re_OldPlayerInfo = re.compile(
        r"^Seat\s(?P<SEAT>\d+):\s(?P<PNAME>.+?)\s\((?P<CASH>[\d.]+)\)(?:\s-\s.+)?\s*$",
        re.MULTILINE,
    )
    re_OldButton = re.compile(r"^(?P<PNAME>.+?) has the dealer button", re.MULTILINE)
    re_OldPostSB = re.compile(r"^(?P<PNAME>.+?) posts small blind (?P<SB>[\d.]+)", re.MULTILINE)
    re_OldPostBB = re.compile(r"^(?P<PNAME>.+?) posts big blind (?P<BB>[\d.]+)", re.MULTILINE)
    re_OldPostBoth = re.compile(r"^(?P<PNAME>.+?) posts small \& big blind (?P<SBBB>[\d.]+)", re.MULTILINE)
    re_OldStreets = re.compile(
        r"\*\* Hole Cards \*\*(?P<PREFLOP>.+?(?=\*\* Flop \*\*)|.+)"
        r"(\*\* Flop \*\*(?P<FLOP>.+?(?=\*\* Turn \*\*)|.+))?"
        r"(\*\* Turn \*\*(?P<TURN>.+?(?=\*\* River \*\*)|.+))?"
        r"(\*\* River \*\*(?P<RIVER>.+?(?=\*\*(?:\sMain Pot| Pot| .+ Pot)? Show Down \*\*)|.+))?",
        re.DOTALL,
    )
    re_OldAction = re.compile(
        r"^(?P<PNAME>.+?)\s(?P<ATYPE>folds|checks|calls|bets|raises)(?:\sto)?"
        r"(?:\s(?P<BET>[\d.]+))?(?:\s\(All-in\))?\s*$",
        re.MULTILINE,
    )
    re_OldUncalled = re.compile(r"^(?P<PNAME>.+?) refunded (?P<BET>[\d.]+)", re.MULTILINE)
    re_OldShown = re.compile(
        r"^(?P<PNAME>.+?) shows \[(?P<CARDS>.+?)\]\s\((?P<STRING>.+?)\)\s*$",
        re.MULTILINE,
    )
    re_OldCollect = re.compile(
        r"^(?P<PNAME>.+?) wins (?:Main Pot|Side Pot \d+|Pot) \((?P<POT>[\d.]+)\)",
        re.MULTILINE,
    )
    re_OldRake = re.compile(r"^Rake \((?P<RAKE>[\d.]+)\)", re.MULTILINE)

    def _is_old_format(self, text) -> bool:
        """True for the legacy 2013 'Seals With Clubs' text format."""
        return self.re_NewFormat.search(text) is None

    def compilePlayerRegexs(self, hand) -> None:
        """Compiles regular expressions to match player names and cards shown in a poker hand.

        Args:
        - self: instance of the class containing the method
        - hand: a Hand object representing the poker hand

        Returns: None

        """
        log.info("Compiling player regexes")
        # Get a set of player names in the hand
        players = {player[1] for player in hand.players}

        # Check if the set of players is a subset of compiledPlayers
        if not players <= self.compiledPlayers:
            # If not, update compiledPlayers
            self.compiledPlayers = players

            # Compile a regular expression to match the player's name
            # The regular expression is of the form "(?P<PNAME>player1|player2|player3)"
            player_re = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"

            # Define substitutions for the regular expressions
            subst = {
                "PLYR": player_re,
                "BRKTS": r"(\(button\) |\(small blind\) |\(big blind\) |\(button\) \(small blind\) |\(button\) \(big blind\) )?",
                "CUR": "(\\$|\xe2\x82\xac|\u20ac||\\£|)",
            }

            # Compile a regular expression to match the cards dealt to the player
            # The regular expression is of the form "^Dealt to %(PLYR)s(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])"
            self.re_HeroCards = re.compile(
                r"^Dealt to {PLYR}(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(**subst),
                re.MULTILINE,
            )

            # Compile a regular expression to match the cards shown by the player
            # The regular expression is of the form "^Seat (?P<SEAT>[0-9]+): %(PLYR)s %(BRKTS)s(?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]( and (lost|(won|collected) \(%(CUR)s(?P<POT>[,\.\d]+)\)) with (?P<STRING>.+?)(,\sand\s(won\s\(%(CUR)s[\.\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?$"
            self.re_ShownCards = re.compile(
                r"^Seat (?P<SEAT>[0-9]+): {PLYR} {BRKTS}(?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]( and (lost|(won|collected) \({CUR}(?P<POT>[,\.\d]+)\)) with (?P<STRING>.+?)(,\sand\s(won\s\({CUR}[\.\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?$".format(
                    **subst
                ),
                re.MULTILINE,
            )

    def readSupportedGames(self):
        log.info("Reading supported games")
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
            ["tour", "hold", "6_holdem"],
        ]

    def determineGameType(self, handText):
        log.info("Determining game type")
        if self._is_old_format(handText):
            return self._determineGameTypeOld(handText)
        info = {}
        m = self.re_GameInfo.search(handText)
        if not m:
            tmp = handText[:200]
            log.error(f"SealsWithClubsToFpdb.determineGameType: '{tmp}'")
            raise FpdbParseError

        mg = m.groupdict()
        log.debug(f"Matched groups: {mg}")
        if "LIMIT" in mg:
            info["limitType"] = self.limits[mg["LIMIT"]]
        if "GAME" in mg:
            (info["base"], info["category"]) = self.games[mg["GAME"]]
        if "SB" in mg:
            if "," in mg["SB"]:
                mg["SB"] = mg["SB"].replace(",", "")
            info["sb"] = mg["SB"]
        if "BB" in mg:
            if "," in mg["BB"]:
                mg["BB"] = mg["BB"].replace(",", "")
            info["bb"] = mg["BB"]
        info["type"] = "ring" if "TOURNO" in mg and mg["TOURNO"] is None else "tour"
        if info["type"] == "ring":
            info["currency"] = "mBTC"
        else:
            info["currency"] = "mBTC"

        if info["limitType"] == "fl" and info["bb"] is not None:
            info["sb"] = str((Decimal(mg["SB"]) / 2).quantize(Decimal("0.01")))
            info["bb"] = str(Decimal(mg["SB"]).quantize(Decimal("0.01")))

        log.debug(f"Game info: {info}")
        return info

    # ------------------------------------------------------------------
    # Legacy 2013 "Seals With Clubs" format helpers
    # ------------------------------------------------------------------
    def _determineGameTypeOld(self, handText):
        m = self.re_OldGameInfo.search(handText)
        if not m:
            tmp = handText[:200]
            log.error(f"SealsWithClubsToFpdb._determineGameTypeOld: '{tmp}'")
            raise FpdbParseError
        mg = m.groupdict()
        info = {
            "limitType": self.limits[mg["LIMIT"]],
            "sb": mg["SB"],
            "bb": mg["BB"],
            "type": "ring",
            "currency": "mBTC",
        }
        (info["base"], info["category"]) = self.games[mg["GAME"]]
        if info["limitType"] == "fl":
            # Limit games report the bet sizes ("Stakes 2/4"); blinds are half.
            info["sb"] = str((Decimal(mg["SB"]) / 2).quantize(Decimal("0.01")))
            info["bb"] = str(Decimal(mg["SB"]).quantize(Decimal("0.01")))
        return info

    def _readHandInfoOld(self, hand) -> None:
        m = self.re_OldGameInfo.search(hand.handText)
        if m is None:
            tmp = hand.handText[:200]
            log.error(f"SealsWithClubsToFpdb._readHandInfoOld: '{tmp}'")
            raise FpdbParseError
        mg = m.groupdict()
        # The legacy hand id is "<session>-<seq>"; siteHandNo is a BIGINT, so
        # fold the two parts into a single collision-free integer.
        main, seq = mg["HID"].split("-")
        hand.handid = str(int(main) * 100000 + int(seq))
        hand.startTime = datetime.datetime.strptime(mg["DATETIME"], "%Y-%m-%d %H:%M:%S")
        hand.startTime = HandHistoryConverter.changeTimezone(hand.startTime, "ET", "UTC")

        if mt := self.re_OldTable.search(hand.handText):
            hand.tablename = mt.group("TABLE")
            if mx := self.re_OldMax.search(mt.group("TABLE")):
                hand.maxseats = 2 if mx.group("HU") else int(mx.group("MAX"))
                hand.gametype["maxSeats"] = hand.maxseats

        if self.re_Cancelled.search(hand.handText):
            msg = f"Hand '{hand.handid}' was cancelled."
            raise FpdbHandPartial(msg)

    def _readPlayerStacksOld(self, hand) -> None:
        plist: dict[str, bool] = {}
        for a in self.re_OldPlayerInfo.finditer(hand.handText):
            if plist.get(a.group("PNAME")) is None:
                hand.addPlayer(int(a.group("SEAT")), a.group("PNAME"), a.group("CASH"))
                plist[a.group("PNAME")] = True
        if len(plist) < 2:
            msg = f"Less than 2 players in hand! {hand.handid}."
            raise FpdbHandPartial(msg)

    def readHandInfo(self, hand) -> None:
        log.info("Reading hand info")
        if self._is_old_format(hand.handText):
            return self._readHandInfoOld(hand)
        info = {}
        m = self.re_HandInfo.search(hand.handText, re.DOTALL)
        m2 = self.re_GameInfo.search(hand.handText)

        if m is None or m2 is None:
            tmp = hand.handText[:200]
            log.error(f"SealsWithClubsToFpdb.readHandInfo: '{tmp}'")
            raise FpdbParseError

        info.update(m.groupdict())
        log.debug(f"HandInfo groups: {m.groupdict()}")
        info.update(m2.groupdict())
        log.debug(f"GameInfo groups: {m2.groupdict()}")

        if info["TOURNO"] is not None:
            words = m["TABLE"].split()
            new_string = words[1]
            info["TABLE"] = f"{m2['TABLE2']} {new_string}"
            log.debug(f"Table name updated to: {info['TABLE']}")
            hand.tablename = f"{info['TABLE']}"
            hand.tourneyName = m2["TABLE2"]
        else:
            # for cash game
            info["TABLE"] = m["TABLE"]
            log.debug(f"Table name for cash game: {info['TABLE']}")
            hand.tablename = f"{info['TABLE']}"

        for key in info:
            if key == "DATETIME":
                m1 = self.re_DateTime.finditer(info[key])
                datetimestr = "2000-01-01 00:00:00"
                for a in m1:
                    datetimestr = "{}-{}-{} {}:{}:{}".format(
                        a.group("Y"),
                        a.group("M"),
                        a.group("D"),
                        a.group("H"),
                        a.group("MIN"),
                        a.group("S"),
                    )
                hand.startTime = datetime.datetime.strptime(
                    datetimestr,
                    "%Y-%m-%d %H:%M:%S",
                )
                hand.startTime = HandHistoryConverter.changeTimezone(
                    hand.startTime,
                    "ET",
                    "UTC",
                )
            if key == "HID":
                hand.handid = info[key]
                log.debug(f"Hand ID: {hand.handid}")
            if key == "TOURNO":
                hand.tourNo = info[key]
            if key == "BUYIN" and hand.tourNo is not None:
                if info[key] == "Freeroll":
                    hand.buyin = 0
                    hand.fee = 0
                    hand.buyinCurrency = "FREE"
                else:
                    hand.buyinCurrency = "mBTC"
                    hand.buyin = int(100 * Decimal(info["BIAMT"]))
                    hand.fee = int(100 * Decimal(info["BIRAKE"]))
            if key == "LEVEL":
                hand.level = info[key]
            if key == "MAX" and info[key] is not None:
                hand.maxseats = int(info[key])
                hand.gametype["maxSeats"] = hand.maxseats
            if key == "HU" and info[key] is not None:
                hand.maxseats = 2
                hand.gametype["maxSeats"] = hand.maxseats

        log.debug(f"Final hand info: {info}")

        if not hand.handid:
            log.error("Hand ID not found, unable to process hand.")
            msg = "Hand ID not found."
            raise FpdbParseError(msg)

        if self.re_Cancelled.search(hand.handText):
            msg = f"Hand '{hand.handid}' was cancelled."
            raise FpdbHandPartial(msg)

    def readButton(self, hand) -> None:
        log.info("Reading button position")
        if self._is_old_format(hand.handText):
            if m := self.re_OldButton.search(hand.handText):
                bname = m.group("PNAME")
                for seat, pname, _stack in (
                    (p[0], p[1], p[2]) for p in hand.players
                ):
                    if pname == bname:
                        hand.buttonpos = seat
                        break
            return
        if m := self.re_ButtonPos.search(hand.handText):
            hand.buttonpos = int(m.group("BUTTON"))
        else:
            log.debug("readButton: not found")

    def readPlayerStacks(self, hand) -> None:
        if self._is_old_format(hand.handText):
            return self._readPlayerStacksOld(hand)
        handsplit = hand.handText.split("*** SUMMARY ***")
        if len(handsplit) != 2:
            self.raise_summary_partial(hand, "*** SUMMARY ***")
        pre, post = handsplit
        m = self.re_PlayerInfo.finditer(pre)
        plist: dict[str, list[int | str]] = {}

        for a in m:
            if plist.get(a.group("PNAME")) is None:
                hand.addPlayer(int(a.group("SEAT")), a.group("PNAME"), a.group("CASH"))
                plist[a.group("PNAME")] = [int(a.group("SEAT")), a.group("CASH")]

        if len(plist.keys()) < 2:
            msg = f"Less than 2 players in hand! {hand.handid}."
            raise FpdbHandPartial(msg)

    def markStreets(self, hand) -> None:
        log.info("Marking streets")
        if self._is_old_format(hand.handText):
            m = self.re_OldStreets.search(hand.handText)
            if not m:
                raise FpdbParseError
            hand.addStreets(m)
            return
        if self._mark_double_board_streets(hand):
            return
        if self.re_Turn.search(hand.handText) and not self.re_Flop.search(
            hand.handText,
        ):
            raise FpdbParseError
        if self.re_River.search(hand.handText) and not self.re_Turn.search(
            hand.handText,
        ):
            raise FpdbParseError

        m = re.search(
            r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>[\s\S]*?(?=\*\*\* FLOP \*\*\*)|.+)"
            r"(\*\*\* FLOP \*\*\*(?P<FLOP>[\s\S]*?(?=\*\*\* TURN \*\*\*)|.+))?"
            r"(\*\*\* TURN \*\*\*(?P<TURN>[\s\S]*?(?=\*\*\* RIVER \*\*\*)|.+))?"
            r"(\*\*\* RIVER \*\*\*(?P<RIVER>[\s\S]*?(?=\*\*\* SHOW DOWN \*\*\*)|.+))?",
            hand.handText,
            re.DOTALL,
        )

        if not m:
            raise FpdbParseError

        hand.addStreets(m)

    def _double_board_naming(self, hand_text: str) -> tuple[str, str] | None:
        """The naming this hand uses for its two boards, or None if it has one board.

        Only a hand that names a *second flop* is double-board; a hand naming a
        second turn but no second flop is malformed and is left to the ordinary
        single-board path rather than half-parsed.
        """
        for first, second in self.DOUBLE_BOARD_NAMING:
            second_flop = f"*** {second.format(street='FLOP')} ***"
            first_flop = f"*** {first.format(street='FLOP')} ***"
            if second_flop in hand_text and first_flop in hand_text:
                return (first, second)
        return None

    def _mark_double_board_streets(self, hand) -> bool:
        """Split a double-board hand into per-board streets. False if it has one board.

        A double board is dealt once and bet once: both runouts are shown, then
        the single betting round follows. So each street's *actions* belong to the
        base street (FLOP/TURN/RIVER, board one) and the second board contributes
        only its cards, on FLOP2/TURN2/RIVER2 -- the same shape the SwC live
        capture already produces (see http_capture_hand_builder._board_streets),
        which keeps Hands.boardcard1..5 pointing at board one and lets
        DerivedStats.getBoardsList encode both runs into the Boards table.

        Without this, a double-board hand matched none of the single-board street
        markers, so PREFLOP swallowed the whole hand: no board, no postflop
        action, no showdown -- the "partial import".

        Note that no SwC history seen so far names a second board: on a real
        "Double Board Bomb Pots" table the client writes one board and pays out
        for two (see readOther). This path therefore does not fire on SwC today;
        it is kept because the SwC grammar is PokerStars-derived, so it would
        start working the day the room writes the second board like every other
        room in this codebase does.
        """
        naming = self._double_board_naming(hand.handText)
        if naming is None:
            return False
        first, second = naming

        # Every board header, in the order the client wrote them, so each block
        # runs to whichever header comes next.
        headers: list[tuple[str, str]] = []  # (street key, marker)
        for street in self.BOARD_STREETS:
            for template, suffix in ((first, ""), (second, "2")):
                marker = f"*** {template.format(street=street)} ***"
                if marker in hand.handText:
                    headers.append((f"{street}{suffix}", marker))
        headers.sort(key=lambda h: hand.handText.index(h[1]))

        hole = re.search(r"\*\*\* HOLE CARDS \*\*\*", hand.handText)
        if hole is None or not headers:
            return False

        # Boundaries: each block ends where the next header (or the showdown /
        # summary) begins.
        stops = [hand.handText.index(marker) for _street, marker in headers]
        showdown = re.search(r"\*\*\* (SHOW DOWN|SUMMARY) \*\*\*", hand.handText)
        stops.append(showdown.start() if showdown else len(hand.handText))

        streets = {"PREFLOP": hand.handText[hole.end() : stops[0]]}
        for index, (street, marker) in enumerate(headers):
            start = hand.handText.index(marker) + len(marker)
            streets[street] = hand.handText[start : stops[index + 1]]

        # The betting round follows the *last* board of the street, so move it
        # onto the base street and leave the extra board its header cards only.
        for street in self.BOARD_STREETS:
            extra = f"{street}2"
            if street in streets and extra in streets:
                actions = streets[extra].split("\n", 1)
                streets[extra] = actions[0]
                if len(actions) > 1:
                    streets[street] = streets[street].rstrip("\n") + "\n" + actions[1]

        hand.streets.update(streets)
        hand.runItTimes = 2
        log.info("Double board hand %s: streets %s", hand.handid, sorted(streets))
        return True

    def readCommunityCards(self, hand, street) -> None:
        log.debug(f"Reading community cards for street: {street}")
        # A double board puts its extra runout on FLOP2/TURN2/RIVER2.
        if street.rstrip("123456789") in self.BOARD_STREETS:
            street_header = hand.streets[street].splitlines()[0]
            brackets = re.findall(r"\[([^\]]+)\]", street_header)
            if brackets:
                cards_str = brackets[-1]
                cards = [card.strip() for card in cards_str.split() if card.strip()]
                hand.setCommunityCards(street, cards)

    def readAntes(self, hand) -> None:
        log.info("Reading antes")
        m = self.re_Antes.finditer(hand.handText)
        for player in m:
            log.debug(f"hand.addAnte({player.group('PNAME')},{player.group('ANTE')})")
            hand.addAnte(player.group("PNAME"), player.group("ANTE"))

    def readBlinds(self, hand) -> None:
        log.debug("Reading blinds")
        if self._is_old_format(hand.handText):
            liveBlind = True
            for a in self.re_OldPostSB.finditer(hand.handText):
                if liveBlind:
                    hand.addBlind(a.group("PNAME"), "small blind", a.group("SB"))
                    liveBlind = False
                else:
                    hand.addBlind(a.group("PNAME"), "secondsb", a.group("SB"))
            for a in self.re_OldPostBB.finditer(hand.handText):
                hand.addBlind(a.group("PNAME"), "big blind", a.group("BB"))
            for a in self.re_OldPostBoth.finditer(hand.handText):
                hand.addBlind(a.group("PNAME"), "both", a.group("SBBB"))
            return
        liveBlind = True
        for a in self.re_PostSB.finditer(hand.handText):
            if liveBlind:
                hand.addBlind(a.group("PNAME"), "small blind", a.group("SB"))
                liveBlind = False
            else:
                hand.addBlind(a.group("PNAME"), "secondsb", a.group("SB"))
        for a in self.re_PostBB.finditer(hand.handText):
            hand.addBlind(a.group("PNAME"), "big blind", a.group("BB"))
        for a in self.re_PostBoth.finditer(hand.handText):
            hand.addBlind(a.group("PNAME"), "both", a.group("SBBB"))

    def readHoleCards(self, hand) -> None:
        log.debug("Reading hole cards")
        for street in ("PREFLOP", "DEAL"):
            if street in list(hand.streets.keys()):
                m = self.re_HeroCards.finditer(hand.streets[street])
                for found in m:
                    hand.hero = found.group("PNAME")
                    newcards = found.group("NEWCARDS").split(" ")
                    hand.addHoleCards(
                        street,
                        hand.hero,
                        closed=newcards,
                        shown=False,
                        mucked=False,
                        dealt=True,
                    )

    def readAction(self, hand, street) -> None:
        log.debug(f"Reading actions for street: {street}")
        if self._is_old_format(hand.handText):
            for action in self.re_OldAction.finditer(hand.streets[street]):
                atype = action.group("ATYPE")
                pname = action.group("PNAME")
                if atype == "folds":
                    hand.addFold(street, pname)
                elif atype == "checks":
                    hand.addCheck(street, pname)
                elif atype == "calls":
                    hand.addCall(street, pname, action.group("BET"))
                elif atype == "raises":
                    hand.addRaiseTo(street, pname, action.group("BET"))
                elif atype == "bets":
                    hand.addBet(street, pname, action.group("BET"))
            return
        m = self.re_Action.finditer(hand.streets[street])
        for action in m:
            acts = action.groupdict()
            log.debug(f"Action details: {acts}")
            if action.group("ATYPE") == " folds":
                hand.addFold(street, action.group("PNAME"))
            elif action.group("ATYPE") == " checks":
                hand.addCheck(street, action.group("PNAME"))
            elif action.group("ATYPE") == " calls":
                hand.addCall(street, action.group("PNAME"), action.group("BET"))
            elif action.group("ATYPE") == " raises":
                # "raises 0.06 to 0.08": the first figure is what the raise adds,
                # the second is what the player is now in for. addRaiseTo wants
                # the second -- fed the first, the raiser was recorded as having
                # put in less than he called with.
                hand.addRaiseTo(street, action.group("PNAME"), action.group("POT") or action.group("BET"))
            elif action.group("ATYPE") == " bets":
                hand.addBet(street, action.group("PNAME"), action.group("BET"))
            else:
                log.debug(
                    f"DEBUG: Unimplemented {action.group('ATYPE')}: '{action.group('PNAME')}'",
                )

        # A bet nobody called goes back to its owner. The summary pot already
        # nets it out, which is why readCollectPot could ignore it, but the
        # player's committed money is what totalProfit is built from: leaving
        # the bet in it booked the winner as having paid it.
        for uncalled_match in self.re_Uncalled.finditer(hand.streets[street]):
            hand.addUncalled(
                street,
                uncalled_match.group("PNAME"),
                uncalled_match.group("BET"),
            )

    def readShownCards(self, hand) -> None:
        log.info("Reading shown cards")
        if self._is_old_format(hand.handText):
            for m in self.re_OldShown.finditer(hand.handText):
                cards = m.group("CARDS").split(" ")
                hand.addShownCards(
                    cards=cards,
                    player=m.group("PNAME"),
                    shown=True,
                    mucked=False,
                    string=m.group("STRING"),
                )
            return
        for m in self.re_ShownCards.finditer(hand.handText):
            if m.group("CARDS") is not None:
                cards = m.group("CARDS").split(" ")
                string = m.group("STRING")
                if m.group("STRING2"):
                    string += "|" + m.group("STRING2")
                (shown, mucked) = (False, False)
                if m.group("SHOWED") == "showed":
                    shown = True
                elif m.group("SHOWED") == "mucked":
                    mucked = True
                hand.addShownCards(
                    cards=cards,
                    player=m.group("PNAME"),
                    shown=shown,
                    mucked=mucked,
                    string=string,
                )

    def readShowdownActions(self, hand) -> None:
        log.info("Reading showdown actions")
        if self._is_old_format(hand.handText):
            return
        for shows in self.re_ShowdownAction.finditer(hand.handText):
            if shows.group("CARDS") is not None:
                cards = shows.group("CARDS").split(" ")
                hand.addShownCards(cards, shows.group("PNAME"))
        for mucks in self.re_CollectPot.finditer(hand.handText):
            if mucks.group("SHOWED") == "mucked" and mucks.group("CARDS") is not None:
                cards = mucks.group("CARDS").split(" ")
                hand.addShownCards(cards, mucks.group("PNAME"))

    def readSummaryInfo(self, summaryInfoList) -> bool:
        log.info("enter method readSummaryInfo.")
        log.debug("Method readSummaryInfo non implemented.")
        return True

    def readBringIn(self, hand) -> None:
        log.info("enter method readBringIn.")
        log.debug("Method readBringIn non implemented.")

    def readSTP(self, hand) -> None:
        """Flag a bomb pot and record the ante money that seeded it.

        SwC deals a bomb pot by taking an ante from every seated player and
        dealing straight to the flop -- no blind is posted and there is no
        preflop betting round. Antes on their own do not make a bomb pot (a
        tournament posts them alongside the blinds), so it is the *absence* of
        any blind posting that separates the two.

        Only ``bombPot`` is set, never ``addSTP``: the money is the players'
        own antes, already counted in the pot through the BLINDSANTES actions,
        and adding it again as room-seeded money would double the pot.
        """
        log.info("enter method readSTP.")
        if self._is_old_format(hand.handText):
            return
        antes = list(self.re_Antes.finditer(hand.handText))
        if not antes:
            return
        for blind in (self.re_PostSB, self.re_PostBB, self.re_PostBoth):
            if blind.search(hand.handText):
                return
        total = sum(Decimal(m.group("ANTE")) for m in antes)
        hand.bombPot = int(total * 100)
        log.info("Bomb pot hand %s seeded with %s from %d antes", hand.handid, total, len(antes))

    def readTourneyResults(self, hand) -> None:
        log.info("enter method readTourneyResults.")
        log.debug("Method readTourneyResults non implemented.")

    def readCollectPot(self, hand) -> None:
        log.info("Reading collected pot")

        if self._is_old_format(hand.handText):
            # Old format has no summary line; let Hand compute the pot from the
            # bets and derive the rake from pot - collected. Refunds appear as
            # "X refunded N" and are handled as uncalled bets.
            for m in self.re_OldCollect.finditer(hand.handText):
                hand.addCollectPot(player=m.group("PNAME"), pot=m.group("POT"))
            return

        # Get rake and total pot from summary FIRST
        rake = Decimal(0)
        totalpot_from_summary = Decimal(0)

        if self.re_rake.search(hand.handText) is not None:
            for m in self.re_rake.finditer(hand.handText):
                rake = rake + Decimal(m.group("RAKE"))
                if "," in m.group("TOTALPOT"):
                    newtotalpot = m.group("TOTALPOT").replace(",", "")
                    totalpot_from_summary = totalpot_from_summary + Decimal(newtotalpot)
                else:
                    totalpot_from_summary = totalpot_from_summary + Decimal(m.group("TOTALPOT"))

        # For SealsWithClubs, the total pot in summary is the actual total pot
        # It already includes everything (main pot, side pots, uncalled bets)
        # We trust this value instead of recalculating
        hand.totalpot = totalpot_from_summary

        # Now collect all pots won by players
        for m in self.re_CollectPot.finditer(hand.handText):
            if m.group("POT") is not None:
                hand.addCollectPot(player=m.group("PNAME"), pot=m.group("POT").replace(",", ""))
            elif m.group("POT2") is not None:
                hand.addCollectPot(player=m.group("PNAME"), pot=m.group("POT2").replace(",", ""))

        # Set rake
        if hand.rake is None:
            hand.rake = rake
        elif hand.rakes.get("rake"):
            hand.rakes["rake"] += rake
        else:
            hand.rakes["rake"] = rake

    @staticmethod
    def getTableTitleRe(
        type,
        table_name=None,
        tournament=None,
        table_number=None,
        tourney_name=None,
        **kwargs,
    ):
        log.debug(
            f"Seals.getTableTitleRe: table_name='{table_name}' tournament='{tournament}' table_number='{table_number}' tourney_name='{tourney_name}'",
        )

        if not table_name:
            if tourney_name:
                table_name = f"{tourney_name} {table_number}"
            elif tournament is not None and table_number is not None:
                table_name = f"{tournament} {table_number}"
            else:
                log.debug("Seals.getTableTitleRe: no valid input provided")
                return ""

        log.debug(f"Initial table_name: {table_name}")

        regex = f"{table_name}"
        words = regex.split()

        if type in ["tour", "ring"]:
            if len(words) > 2:
                regex = " ".join(words[1:-1])
            log.debug(f"Seals.getTableTitleRe: regex after processing='{regex}'")
            import re
            return re.escape(regex)

        regex = f"{table_name}"
        log.debug(f"Seals.getTableTitleRe: regex='{regex}'")
        import re
        return re.escape(regex)

    def readOther(self, hand: Hand) -> None:
        """Report a bomb pot whose payouts prove a board the history never wrote.

        Observed on a real "Double Board Bomb Pots" table (hand 301461492): three
        antes of 0.12 make a 0.36 pot, one board ``[3d 2h 9c 6d Ah]`` is written,
        and on it Folded74Dice's two pair beats edinapoker's pair outright -- yet
        the room pays 0.27 and 0.09. That split only resolves as two boards of
        0.18: the written one won outright (0.18), and a *second, unwritten* one
        chopped (0.09 each). So the SwC text history drops the second board of a
        double board while its payouts still reflect both.

        Nothing can recover those cards from the text, and inventing them would
        be worse than missing them (DerivedStats.getBoardsList falls back to the
        first board for a missing run, which would store board one twice as if it
        were dealt twice). This only says so in the log, so the hands that are
        incomplete at the source can be told from the ones fpdb mis-parsed.

        Unequal payouts are the detectable case. Two boards each won outright by
        a different player pay equally and are indistinguishable from an ordinary
        single-board chop, so they are not reported.
        """
        if not getattr(hand, "bombPot", 0) or len(hand.collectees) < 2:
            return
        if "and is all-in" in hand.handText:
            # A side pot pays different players different amounts for reasons
            # that have nothing to do with a second board.
            return
        amounts = set(hand.collectees.values())
        if len(amounts) > 1:
            log.warning(
                "SwC bomb pot %s pays %s from a single written board: the history omitted "
                "the second board of a double board, so this hand's board data is incomplete",
                hand.handid,
                dict(hand.collectees),
            )
