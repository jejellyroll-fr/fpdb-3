"""Betfair poker hand history parser for FPDB.

Copyright 2008-2011, Carl Gherardi

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
from typing import Any

from HandHistoryConverter import FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger

log = get_logger("parser")

# Betfair HH format


class Betfair(HandHistoryConverter):
    """Betfair poker hand history converter."""
    sitename = "Betfair"
    filetype = "text"
    codepage = "cp1252"
    site_id = 7  # Needs to match id entry in Sites database

    # Static regexes
    re_game_info = re.compile(
        r"^(?P<LIMIT>NL|PL|) (?P<CURRENCY>\$|)?(?P<SB>[.0-9]+)/\$?(?P<BB>[.0-9]+) "
        r"(?P<GAME>(Texas Hold'em|Omaha Hi|Omaha|Razz))",
        re.MULTILINE,
    )
    re_identify = re.compile(r"\*{5}\sBetfair\sPoker\sHand\sHistory\sfor\sGame\s\d+\s")
    re_split_hands = re.compile(r"\n\n+")
    re_hand_info = re.compile(
        r"\*\*\*\*\* Betfair Poker Hand History for Game (?P<HID>[0-9]+) \*\*\*\*\*\n"
        r"(?P<LIMIT>NL|PL|) (?P<CURRENCY>\$|)?(?P<SB>[.0-9]+)/\$?(?P<BB>[.0-9]+) "
        r"(?P<GAMETYPE>(Texas Hold'em|Omaha|Razz)) - "
        r"(?P<DATETIME>[a-zA-Z]+, [a-zA-Z]+ \d+, \d\d:\d\d:\d\d GMT \d\d\d\d)\n"
        r"Table (?P<TABLE>[ a-zA-Z0-9]+) \d-max \(Real Money\)\n"
        r"Seat (?P<BUTTON>[0-9]+)",
        re.MULTILINE,
    )
    re_button = re.compile(r"^Seat (?P<BUTTON>\d+) is the button", re.MULTILINE)
    re_player_info = re.compile(
        r"Seat (?P<SEAT>[0-9]+): (?P<PNAME>.*)\s\(\s(\$(?P<CASH>[.0-9]+)) \)",
    )
    re_board = re.compile(r"\[ (?P<CARDS>.+) \]")

    def compilePlayerRegexs(self, hand: Any) -> None:
        """Compile player-specific regex patterns."""
        players = {player[1] for player in hand.players}
        if not players <= self.compiledPlayers:  # x <= y means 'x is subset of y'
            # we need to recompile the player regexs.
            self.compiledPlayers = players
            player_re = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"
            log.debug("player_re: %s", player_re)
            self.re_post_sb = re.compile(
                rf"^{player_re} posts small blind \[\$?(?P<SB>[.0-9]+)",
                re.MULTILINE,
            )
            self.re_post_bb = re.compile(
                rf"^{player_re} posts big blind \[\$?(?P<BB>[.0-9]+)",
                re.MULTILINE,
            )
            self.re_antes = re.compile(
                f"^{player_re} antes asdf sadf sadf",
                re.MULTILINE,
            )
            self.re_bring_in = re.compile(
                f"^{player_re} antes asdf sadf sadf",
                re.MULTILINE,
            )
            self.re_post_both = re.compile(
                rf"^{player_re} posts small \& big blinds \[\$?(?P<SBBB>[.0-9]+)",
                re.MULTILINE,
            )
            self.re_hero_cards = re.compile(
                rf"^Dealt to {player_re} \[ (?P<CARDS>.*) \]",
                re.MULTILINE,
            )
            self.re_action = re.compile(
                rf"^{player_re} (?P<ATYPE>bets|checks|raises to|raises|calls|folds)(\s\[\$(?P<BET>[.\d]+)\])?",
                re.MULTILINE,
            )
            self.re_showdown_action = re.compile(
                rf"^{player_re} shows \[ (?P<CARDS>.*) \]",
                re.MULTILINE,
            )
            self.re_collect_pot = re.compile(
                rf"^{player_re} wins \$(?P<POT>[.\d]+) (.*?\[ (?P<CARDS>.*?) \])?",
                re.MULTILINE,
            )
            self.re_sits_out = re.compile(f"^{player_re} sits out", re.MULTILINE)
            self.re_shown_cards = re.compile(
                rf"{player_re} (?P<SEAT>[0-9]+) (?P<CARDS>adsfasdf)",
                re.MULTILINE,
            )

    def readSupportedGames(self) -> list[list[str]]:
        """Return list of supported game types."""
        return [["ring", "hold", "nl"], ["ring", "hold", "pl"]]

    def determineGameType(self, hand_text: str) -> dict[str, Any]:
        """Determine the game type from hand text."""
        info = {"type": "ring"}

        m = self.re_game_info.search(hand_text)
        if not m:
            tmp = hand_text[0:200]
            log.error("determineGameType not found: '%s'", tmp)
            raise FpdbParseError

        mg = m.groupdict()

        # translations from captured groups to our info strings
        limits = {"NL": "nl", "PL": "pl", "Limit": "fl"}
        games = {  # base, category
            "Texas Hold'em": ("hold", "holdem"),
            "Omaha Hi": ("hold", "omahahi"),
            "Omaha": ("hold", "omahahi"),
            "Razz": ("stud", "razz"),
            "7 Card Stud": ("stud", "studhi"),
        }
        currencies = {" €": "EUR", "$": "USD", "": "T$"}
        if "LIMIT" in mg:
            info["limitType"] = limits[mg["LIMIT"]]
        if "GAME" in mg:
            (info["base"], info["category"]) = games[mg["GAME"]]
        if "SB" in mg:
            info["sb"] = mg["SB"]
        if "BB" in mg:
            info["bb"] = mg["BB"]
        if "CURRENCY" in mg:
            info["currency"] = currencies[mg["CURRENCY"]]

        return info

    def readHandInfo(self, hand: Any) -> None:
        """Read basic hand information."""
        m = self.re_hand_info.search(hand.handText)
        if m is None:
            tmp = hand.handText[0:200]
            log.error("determineGameType not found: '%s'", tmp)
            raise FpdbParseError
        log.debug("HID %s, Table %s", m.group("HID"), m.group("TABLE"))
        hand.handid = m.group("HID")
        hand.tablename = m.group("TABLE")
        hand.startTime = datetime.datetime.strptime(
            m.group("DATETIME"),
            "%A, %B %d, %H:%M:%S GMT %Y",
        ).replace(tzinfo=datetime.timezone.utc)

    def readPlayerStacks(self, hand: Any) -> None:
        """Read player stacks from hand text."""
        m = self.re_player_info.finditer(hand.handText)
        for a in m:
            hand.addPlayer(int(a.group("SEAT")), a.group("PNAME"), a.group("CASH"))

        # Shouldn't really dip into the Hand object, but i've no idea how to tell the length of iter m
        min_players = 2
        if len(hand.players) < min_players:
            log.info("Less than 2 players found in hand %s.", hand.handid)

    def markStreets(self, hand: Any) -> None:
        """Mark the different streets in the hand."""
        m = re.search(
            r"\*\* Dealing down cards \*\*(?P<PREFLOP>.+(?=\*\* Dealing Flop \*\*)|.+)"
            r"(\*\* Dealing Flop \*\*(?P<FLOP> \[ \S\S, \S\S, \S\S \].+(?=\*\* Dealing Turn \*\*)|.+))?"
            r"(\*\* Dealing Turn \*\*(?P<TURN> \[ \S\S \].+(?=\*\* Dealing River \*\*)|.+))?"
            r"(\*\* Dealing River \*\*(?P<RIVER> \[ \S\S \].+))?",
            hand.handText,
            re.DOTALL,
        )

        hand.addStreets(m)

    def readCommunityCards(
        self,
        hand: Any,
        street: str,
    ) -> None:
        """Read community cards for a given street."""
        # street has been matched by markStreets, so exists in this hand
        if street in (
            "FLOP",
            "TURN",
            "RIVER",
        ):  # a list of streets which get dealt community cards (i.e. all but PREFLOP)
            m = self.re_board.search(hand.streets[street])
            hand.setCommunityCards(street, m.group("CARDS").split(", "))

    def readBlinds(self, hand: Any) -> None:
        """Read blind information from hand text."""
        try:
            m = self.re_post_sb.search(hand.handText)
            hand.addBlind(m.group("PNAME"), "small blind", m.group("SB"))
        except AttributeError:
            hand.addBlind(None, None, None)
        for a in self.re_post_bb.finditer(hand.handText):
            hand.addBlind(a.group("PNAME"), "big blind", a.group("BB"))
        for a in self.re_post_both.finditer(hand.handText):
            hand.addBlind(a.group("PNAME"), "small & big blinds", a.group("SBBB"))

    def readAntes(self, hand: Any) -> None:
        """Read ante information from hand text."""
        log.debug("reading antes")
        m = self.re_antes.finditer(hand.handText)
        for player in m:
            log.debug("hand.addAnte(%s,%s)", player.group("PNAME"), player.group("ANTE"))
            hand.addAnte(player.group("PNAME"), player.group("ANTE"))

    def readBringIn(self, hand: Any) -> None:
        """Read bring-in information from hand text."""
        m = self.re_bring_in.search(hand.handText, re.DOTALL)
        if m:
            log.debug(
                "Player bringing in: %s for %s", m.group("PNAME"), m.group("BRINGIN"),
            )
            hand.addBringIn(m.group("PNAME"), m.group("BRINGIN"))
        else:
            log.warning("No bringin found")

    def readButton(self, hand: Any) -> None:
        """Read button position from hand text."""
        hand.buttonpos = int(self.re_button.search(hand.handText).group("BUTTON"))

    def readHoleCards(self, hand: Any) -> None:
        """Read hole cards from hand text."""
        #    streets PREFLOP, PREDRAW, and THIRD are special cases beacause
        #    we need to grab hero's cards
        for street in ("PREFLOP", "DEAL"):
            if street in list(hand.streets.keys()):
                m = self.re_hero_cards.finditer(hand.streets[street])
                for found in m:
                    hand.hero = found.group("PNAME")
                    newcards = [c.strip() for c in found.group("CARDS").split(",")]
                    hand.addHoleCards(
                        street,
                        hand.hero,
                        closed=newcards,
                        shown=False,
                        mucked=False,
                        dealt=True,
                    )

    def readStudPlayerCards(self, hand: Any, street: str) -> None:
        """Read stud player cards (not implemented)."""
        # Not implemented for Betfair

    def readAction(self, hand: Any, street: str) -> None:
        """Read player actions for a given street."""
        m = self.re_action.finditer(hand.streets[street])
        for action in m:
            if action.group("ATYPE") == "folds":
                hand.addFold(street, action.group("PNAME"))
            elif action.group("ATYPE") == "checks":
                hand.addCheck(street, action.group("PNAME"))
            elif action.group("ATYPE") == "calls":
                hand.addCall(street, action.group("PNAME"), action.group("BET"))
            elif action.group("ATYPE") == "bets":
                hand.addBet(street, action.group("PNAME"), action.group("BET"))
            elif action.group("ATYPE") == "raises to":
                hand.addRaiseTo(street, action.group("PNAME"), action.group("BET"))
            else:
                log.debug(
                    "Unimplemented readAction: '%s' '%s'", action.group("PNAME"), action.group("ATYPE"),
                )

    def readSummaryInfo(self, summary_info_list: list[Any]) -> bool:  # noqa: ARG002
        """Read summary information (not implemented)."""
        log.info("enter method readSummaryInfo.")
        log.debug("Method readSummaryInfo non implemented.")
        return True

    def readShowdownActions(self, hand: Any) -> None:
        """Read showdown actions from hand text."""
        for shows in self.re_showdown_action.finditer(hand.handText):
            cards = shows.group("CARDS")
            cards = cards.split(", ")
            hand.addShownCards(cards, shows.group("PNAME"))

    def readCollectPot(self, hand: Any) -> None:
        """Read pot collection information."""
        for m in self.re_collect_pot.finditer(hand.handText):
            hand.addCollectPot(player=m.group("PNAME"), pot=m.group("POT"))

    def readShownCards(self, hand: Any) -> None:
        """Read shown cards from hand text."""
        for m in self.re_shown_cards.finditer(hand.handText):
            if m.group("CARDS") is not None:
                cards = m.group("CARDS")
                cards = cards.split(", ")
                hand.addShownCards(
                    cards=None,
                    player=m.group("PNAME"),
                    holeandboard=cards,
                )

    def readSTP(self, hand: Any) -> None:
        """Read STP (Sit and Go) information (not implemented)."""
        pass

    def readTourneyResults(self, hand: Any) -> None:
        """Read tournament results (not implemented)."""
        pass
