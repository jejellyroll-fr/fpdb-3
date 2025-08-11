"""Cake Network hand history parser.

This module provides functionality to parse hand history files from the Cake Network
and convert them to FPDB format.
"""

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
import re
from decimal import Decimal
from re import Match
from typing import TYPE_CHECKING, ClassVar

from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger

if TYPE_CHECKING:
    from Hand import Hand

log = get_logger("cake_parser")


class Cake(HandHistoryConverter):
    """A class for converting Cake hand histories to FPDB format.

    Inherits from HandHistoryConverter.

    Class Variables:
        sitename (str): The name of the site.
        filetype (str): The file type of the hand history.
        codepage (tuple): The supported code pages for the hand history.
        siteId (int): The ID of the site.
        sym (dict): A dictionary mapping currencies to their symbols.
        substitutions (dict): A dictionary mapping shorthand codes to regular expressions for parsing hand histories.
    """

    # Class Variables

    sitename = "Cake"
    filetype = "text"
    codepage = ("utf8", "cp1252")
    site_id = 17
    sym: ClassVar[dict[str, str]] = {"USD": r"\$", "CAD": r"\$", "T$": "", "EUR": "€", "GBP": "\xa3", "play": ""}
    substitutions: ClassVar[dict[str, str]] = {
        "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP",  # legal ISO currency codes
        "LS": r"\$|€|",  # legal currency symbols - Euro(cp1252, utf-8)
        "PLYR": r"(?P<PNAME>.+?)",
        "CUR": r"(\\\$|€|)?",
        "NUM": r"0-9,\.",
        "NUM2": r"\b((?:\d{1,3}(?:\s\d{3})*)|(?:\d+))\b",  # Regex pattern for matching numbers with spaces
    }

    # translations from captured groups to fpdb info strings
    lim_blinds: ClassVar[dict[str, tuple[str, str]]] = {
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
        "6.00": ("1.50", "3.00"),
        "6": ("1.50", "3.00"),
        "8.00": ("2.00", "4.00"),
        "8": ("2.00", "4.00"),
        "10.00": ("2.50", "5.00"),
        "10": ("2.50", "5.00"),
        "12.00": ("3.00", "6.00"),
        "12": ("3.00", "6.00"),
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
        "200.00": ("50.00", "100.00"),
        "200": ("50.00", "100.00"),
        "400.00": ("100.00", "200.00"),
        "400": ("100.00", "200.00"),
        "800.00": ("200.00", "400.00"),
        "800": ("200.00", "400.00"),
        "1000.00": ("250.00", "500.00"),
        "1000": ("250.00", "500.00"),
    }

    limits: ClassVar[dict[str, str]] = {"NL": "nl", "PL": "pl", "FL": "fl"}
    games: ClassVar[dict[str, tuple[str, str]]] = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi/Lo": ("hold", "omahahilo"),
        "OmahaHiLo": ("hold", "omahahilo"),
    }
    currencies: ClassVar[dict[str, str]] = {"€": "EUR", "$": "USD", "": "T$"}

    # Static regexes - Tournament format (with explicit buyin structure)
    re_game_info_tournament = re.compile(
        r"(?:ï»¿)?Hand\#(?P<HID>[A-Z0-9]+)\s+\-\s+(?P<TOURNAMENT_INFO>.+?)\s+T(?P<TOURNO>\d+)\s+\-\-\s+"
        r"(?P<BUYIN_TYPE>CASH|TICKET|TICKETCASH)\s+\-\-\s+"
        r"(?P<BUYIN>[\$€£]?[0-9,\.]+)\s*\+\s*(?P<FEE>[\$€£]?[0-9,\.]+)\s+\-\-\s+"
        r"(?P<MAXSEATS>\d+)\s+Max\s+\-\-\s+Table\s+(?P<TABLENO>\d+)\s+\-\-\s+"
        r"(?P<ANTE>[\-0-9,\.]+)[/,](?P<SB>[0-9,\.]+)[/,](?P<BB>[0-9,\.]+)\s+"
        r"(?P<LIMIT>NL|FL|PL)\s+(?P<GAME>Hold\'em|Omaha|OmahaHiLo|Omaha\sHi/Lo)\s+\-\-\s+"
        r"(?P<DATETIME>.*?)$",
        re.MULTILINE,
    )

    # Static regexes - Simple tournament format (without explicit buyin structure)
    re_game_info_tournament_simple = re.compile(
        r"(?:ï»¿)?Hand\#(?P<HID>[A-Z0-9]+)\s+\-\s+(?P<TOURNAMENT_INFO>.+?)\s+T(?P<TOURNO>\d+)\s+\-\-\s+"
        r"Table\s+(?P<TABLENO>\d+)\s+\-\-\s+"
        r"(?P<ANTE>[\-0-9,\.]+)[/,](?P<SB>[0-9,\.]+)[/,](?P<BB>[0-9,\.]+)\s+"
        r"(?P<LIMIT>NL|FL|PL)\s+(?P<GAME>Hold\'em|Omaha|OmahaHiLo|Omaha\sHi/Lo)\s+\-\-\s+"
        r"(?P<DATETIME>.*?)$",
        re.MULTILINE,
    )

    # Static regexes - Cash game format
    re_game_info_cash = re.compile(
        r"(?:ï»¿)?Hand\#(?P<HID>[A-Z0-9]+)\s+\-\s+(?P<TABLE>.+?)\s+(?P<TABLENO>\d+)\s+\-\-\s+"
        r"(?P<CURRENCY>[$€£])?(?P<SB>[0-9,\.]+)[/,](?P<CURRENCY2>[$€£])?(?P<BB>[0-9,\.]+)\s+"
        r"(?P<LIMIT>NL|FL|PL)\s+(?P<GAME>Hold\'em|Omaha|Omaha\sHi/Lo|OmahaHiLo)\s+\-\-\s+"
        r"(?P<DATETIME>.*?)$",
        re.MULTILINE,
    )

    re_player_info = re.compile(
        r"^Seat\s(?P<SEAT>[0-9]+):\s(?P<PNAME>.+?)\s\([$]?(?P<CASH>[0-9,\.\s]+)\sin\schips\)\s*(DEALER)?",
        re.MULTILINE,
    )

    re_trim = re.compile(r"(Hand\#)")
    re_identify = re.compile(r"Hand\#[A-Z0-9]+\s\-\s")
    re_split_hands = re.compile("\n\n+")
    re_button = re.compile(r"Dealer: Seat (?P<BUTTON>\d+)", re.MULTILINE)
    re_board = re.compile(r"\[(?P<CARDS>.+)\]")

    re_date_time = re.compile(
        r"""(?P<Y>[0-9]{4})[\/\-\.](?P<M>[0-9]{2})[\/\-\.](?P<D>[0-9]{2})[\- ]+"""
        r"""(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""",
        re.MULTILINE,
    )
    re_post_sb = re.compile(
        r"^{PLYR}: posts small blind {CUR}(?P<SB>[{NUM}]+)(\s\(EUR\s({CUR})?(?P<EUROVALUE>[{NUM}]+)\))?$".format(
            **substitutions,
        ),
        re.MULTILINE,
    )
    re_post_bb = re.compile(
        r"^{PLYR}: posts big blind {CUR}(?P<BB>[{NUM}]+)(\s\(EUR\s({CUR})?(?P<EUROVALUE>[{NUM}]+)\))?$".format(
            **substitutions,
        ),
        re.MULTILINE,
    )
    re_antes = re.compile(
        r"^{PLYR}: posts ante of {CUR}(?P<ANTE>[{NUM}]+)(\s\(EUR\s({CUR})?(?P<EUROVALUE>[{NUM}]+)\))?".format(
            **substitutions,
        ),
        re.MULTILINE,
    )
    re_bring_in = re.compile(
        r"^{PLYR}: brings[- ]in( low|) for {CUR}(?P<BRINGIN>[{NUM}]+)"
        r"(\s\(EUR\s({CUR})?(?P<EUROVALUE>[{NUM}]+)\))?".format(
            **substitutions,
        ),
        re.MULTILINE,
    )
    re_post_both = re.compile(
        r"^{PLYR}:posts dead blind {CUR}(\-)?(?P<SB>[{NUM}]+) and big blind {CUR}(?P<BB>[{NUM}]+)".format(
            **substitutions,
        ),
        re.MULTILINE,
    )
    re_hero_cards = re.compile(
        r"^Dealt to {PLYR}(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(**substitutions),
        re.MULTILINE,
    )
    re_action = re.compile(
        r"""
                        ^{PLYR}:(?P<ATYPE>\sbets|\schecks|\sraises|\scalls|\sfolds|\sis\sall\sin)
                        (\s(to\s)?({CUR})?(?P<BET>[{NUM}]+))?(\s\(EUR\s({CUR})?(?P<EUROVALUE>[{NUM}]+)\))?$
                        """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    re_sits_out = re.compile("^{} sits out".format(substitutions["PLYR"]), re.MULTILINE)
    re_shown_cards = re.compile(
        r"^{}: (?P<SHOWED>shows|mucks) \[(?P<CARDS>.*)\] ?(\((?P<STRING>.*)\))?".format(substitutions["PLYR"]),
        re.MULTILINE,
    )
    re_collect_pot = re.compile(
        r"^{PLYR}:? wins (low pot |high pot )?{CUR}(?P<POT>[{NUM}]+)"
        r"((\swith.+?)?\s+\(EUR\s({CUR})?(?P<EUROVALUE>[{NUM}]+)\))?".format(
            **substitutions,
        ),
        re.MULTILINE,
    )
    re_finished = re.compile(
        r"{PLYR}:? finished \d+ out of \d+ players".format(**substitutions),
        re.MULTILINE,
    )
    re_dealer = re.compile(
        r"Dealer:",
    )  # Some Cake hands just omit the game line so we can just discard them as partial
    re_coin_flip = re.compile(r"Coin\sFlip\sT\d+", re.MULTILINE)
    re_return_bet = re.compile(r"returns\suncalled\sbet", re.MULTILINE)
    re_show_down = re.compile(r"\*\*\*SHOW DOWN\*\*\*")
    re_show_down_left = re.compile(
        r"\*\*\*SHOW\sDOWN\*\*\*\nPlayer\sleft\sthe\stable$",
        re.MULTILINE,
    )

    def compilePlayerRegexs(self, hand: list[str]) -> None:
        """Compiles regular expressions representing the cards in a player's hand.

        Args:
            hand (list[str]): The cards in the player's hand.

        Returns:
            list[re.Pattern]: A list of compiled regular expressions, one for each card in the player's hand.

        """
        # TODO(maintainer): Implement this function.

    def readSupportedGames(self) -> list[list[str]]:
        """Returns a list of supported games.

        Each supported game is represented as a list of game modes.
        """
        return [
            ["ring", "hold", "nl"],  # Ring game, hold mode, no limit
            ["ring", "hold", "pl"],  # Ring game, hold mode, pot limit
            ["ring", "hold", "fl"],  # Ring game, hold mode, fixed limit
            ["tour", "hold", "nl"],  # Tournament, hold mode, no limit
            ["tour", "hold", "pl"],  # Tournament, hold mode, pot limit
            ["tour", "hold", "fl"],  # Tournament, hold mode, fixed limit
        ]

    def determineGameType(self, hand_text: str) -> dict:  # noqa: C901, PLR0912, PLR0915
        """Determine the type of game from the given hand text.

        Args:
            hand_text (str): The text of the hand.

        Returns:
            dict: A dictionary containing information about the game type.

        """
        # Initialize dictionary to store game type info
        info = {}

        # Search for game info in hand text - try tournament formats first
        m = self.re_game_info_tournament.search(hand_text)
        is_tournament = True
        is_simple_tournament = False

        # If full tournament format doesn't match, try simple tournament format
        if not m:
            m = self.re_game_info_tournament_simple.search(hand_text)
            is_simple_tournament = True

        # If no tournament format matches, try cash game format
        if not m:
            m = self.re_game_info_cash.search(hand_text)
            is_tournament = False
            is_simple_tournament = False

        # If no game info found, raise appropriate error
        if not m:
            if self.re_finished.search(hand_text):
                raise FpdbHandPartial
            if self.re_dealer.match(hand_text):
                raise FpdbHandPartial
            tmp = hand_text[:200]
            log.error("determineGameType not found: '%s'", tmp)
            raise FpdbParseError

        # If no ShowDown or ShowDownLeft found, raise appropriate error
        if not self.re_show_down.search(hand_text) or self.re_show_down_left.search(
            hand_text,
        ):
            raise FpdbHandPartial

        # Extract game info from match object's group dictionary
        mg = m.groupdict()

        # Determine limit type and store in info dictionary
        if "LIMIT" in mg:
            info["limitType"] = self.limits[mg["LIMIT"]]

        # Determine game category and base type and store in info dictionary
        if "GAME" in mg:
            (info["base"], info["category"]) = self.games[mg["GAME"]]

        # Determine big blind and store in info dictionary
        if mg.get("BB"):
            info["bb"] = self.clearMoneyString(mg["BB"])

        # Determine small blind and store in info dictionary
        if mg.get("SB"):
            info["sb"] = self.clearMoneyString(mg["SB"])

        # Determine game type and currency based on format
        if is_tournament or is_simple_tournament:
            info["type"] = "tour"

            if is_simple_tournament:
                # Simple tournament format - extract currency from tournament info
                tournament_info = mg.get("TOURNAMENT_INFO", "")
                if "$" in tournament_info:
                    info["currency"] = "USD"
                elif "€" in tournament_info:
                    info["currency"] = "EUR"
                elif "£" in tournament_info:
                    info["currency"] = "GBP"
                elif "FREE" in tournament_info.upper() or "FREEROLL" in tournament_info.upper():
                    info["currency"] = "play"
                else:
                    info["currency"] = "USD"

                # Extract buyin from tournament info for simple format
                buyin_match = re.search(r"[\$€£]([0-9,\.]+)", tournament_info)
                if buyin_match:
                    info["buyin"] = self.clearMoneyString(buyin_match.group(1))
                    info["fee"] = "0"  # No explicit fee in simple format
                else:
                    info["buyin"] = "0"
                    info["fee"] = "0"
            else:
                # Full tournament format - extract currency from buyin
                buyin_type = mg.get("BUYIN_TYPE", "")
                if buyin_type == "TICKET":
                    info["currency"] = "play"
                else:
                    # Extract currency from buyin amount
                    buyin = mg.get("BUYIN", "")
                    if buyin.startswith("$"):
                        info["currency"] = "USD"
                    elif buyin.startswith("€"):
                        info["currency"] = "EUR"
                    elif buyin.startswith("£"):
                        info["currency"] = "GBP"
                    else:
                        info["currency"] = "USD"

                # Tournament specific fields
                if mg.get("BUYIN"):
                    info["buyin"] = self.clearMoneyString(mg["BUYIN"])
                if mg.get("FEE"):
                    info["fee"] = self.clearMoneyString(mg["FEE"])

            # Common tournament fields
            if mg.get("TOURNO"):
                info["tourNo"] = mg["TOURNO"]
        else:
            info["type"] = "ring"
            # Determine currency from cash game format
            currency = mg.get("CURRENCY") or mg.get("CURRENCY2") or ""
            info["currency"] = self.currencies.get(currency, "USD")

            # If play money game, set currency to 'play'
            if "TABLE" in mg and "Play Money" in mg["TABLE"]:
                info["currency"] = "play"

        # For FL games, use the lim_blinds lookup if available
        if info.get("limitType") == "fl" and info.get("bb"):
            try:
                info["sb"] = self.lim_blinds[info["bb"]][0]
                info["bb"] = self.lim_blinds[info["bb"]][1]
            except KeyError:
                # Keep the original values if not in lookup table
                pass

        return info

    def readHandInfo(self, hand: "Hand") -> None:  # noqa: C901
        """Reads information from a hand history string and updates the corresponding Hand object.

        Parameters
        ----------
        hand (Hand): The Hand object to update.

        Returns:
        -------
        None

        """
        # trim off malformatted text from partially written hands
        if not self.re_trim.match(hand.handText):
            hand.handText = "".join(self.re_trim.split(hand.handText)[1:])

        info = {}
        # Try tournament formats first
        m = self.re_game_info_tournament.search(hand.handText)
        if m is None:
            # Try simple tournament format
            m = self.re_game_info_tournament_simple.search(hand.handText)
        if m is None:
            # If no tournament format matches, try cash game format
            m = self.re_game_info_cash.search(hand.handText)

        if m is None:
            tmp = hand.handText[:200]
            log.error("readHandInfo not found: '%s'", tmp)
            raise FpdbParseError

        info |= m.groupdict()

        for key in info:
            # extract datetime information and convert to UTC timezone
            if key == "DATETIME":
                m1 = self.re_date_time.finditer(info[key])
                datetimestr = "2000/01/01 00:00:00"  # default used if time not found
                for a in m1:
                    datetimestr = (
                        f"{a.group('Y')}/{a.group('M')}/{a.group('D')} {a.group('H')}:{a.group('MIN')}:{a.group('S')}"
                    )
                hand.startTime = datetime.datetime.strptime(  # noqa: DTZ007
                    datetimestr,
                    "%Y/%m/%d %H:%M:%S",
                )
                hand.startTime = HandHistoryConverter.changeTimezone(
                    hand.startTime,
                    "ET",
                    "UTC",
                )

            # extract hand ID
            elif key == "HID":
                hand.handid = re.sub("[A-Z]+", "", info[key])

            # extract table name
            if key == "TABLE":
                hand.tablename = info[key]

            # extract table number
            if key == "TABLENO":
                hand.tablename = info[key]


    def readButton(self, hand: "Hand") -> None:
        """Parses a hand for the button position and updates the hand object.

        Args:
            hand (Hand): The hand object to update.

        Returns:
            None

        """
        # Search for the button position in the hand text
        if m := self.re_button.search(hand.handText):
            # If found, update the button position in the hand object
            hand.buttonpos = int(m.group("BUTTON"))
        else:
            # If not found, log an info message
            log.info("readButton: not found")

    def readPlayerStacks(self, hand: "Hand") -> None:
        """Reads player stacks from the given `hand` object and adds them to the `hand` object.

        Args:
            hand (Hand): The `Hand` object to read player stacks from.

        Returns:
            None

        """
        # Find each player's stack information in the hand text
        m = self.re_player_info.finditer(hand.handText)

        # Check if there was a coinflip in the hand
        coinflip = bool(self.re_coin_flip.search(hand.handText))

        # Iterate over each player's stack information
        for a in m:
            # Get cash value from CASH group
            cash_value = a.group("CASH")
            if cash_value:
                cash_value = cash_value.encode("utf-8")
                cash_value = cash_value.replace(b"\xe2\x80\xaf", b"")
                cash_value = cash_value.decode("utf-8")
                # Clean the money string to remove spaces and other formatting
                cash_value = self.clearMoneyString(cash_value)
                log.debug("cleaned value: %s", cash_value)
                log.debug("type: %s", type(cash_value))
                # Add the player's stack information to the `hand` object
                hand.addPlayer(int(a.group("SEAT")), a.group("PNAME"), cash_value)

                # If there was a coinflip, add the ante for the player
                if coinflip:
                    hand.addAnte(a.group("PNAME"), self.convertMoneyString("CASH", a))

    def markStreets(self, hand: "Hand") -> None:
        """Extract street information from hand text and update the hand object.

        Args:
            hand: a Hand object to extract street information from

        Returns:
            None

        """
        # The following regex matches the different streets in a hand history and captures the information
        # in named groups: PREFLOP, FLOP, TURN, RIVER.
        # It first matches everything up to the FLOP street, then optionally matches the FLOP street,
        # then optionally matches the TURN street, and finally optionally matches the RIVER street.
        # The information captured in each street is then stored in its respective named group.
        regex = (
            r"(?P<PREFLOP>.+(?=\*\*\* FLOP \*\*\*)|.+)"
            r"(\*\*\* FLOP \*\*\*(?P<FLOP> \[\S\S,\S\S,\S\S\].+(?=\*\*\* TURN \*\*\*)|.+))?"
            r"(\*\*\* TURN \*\*\* (?P<TURN>\[\S\S\].+(?=\*\*\* RIVER \*\*\*)|.+))?"
            r"(\*\*\* RIVER \*\*\* (?P<RIVER>\[\S\S\].+))?"
        )

        # Use the regex to search for the street information in the hand's handText attribute
        m = re.search(regex, hand.handText, re.DOTALL)

        # Add the street information to the Hand object
        hand.addStreets(m)

    def readCommunityCards(self, hand: "Hand", street: str) -> None:
        """Reads the community cards for a given street of the current hand and sets them in the hand object.

        Args:
            hand (Hand): The current hand object.
            street (str): The street to read the community cards for.

        Returns:
            None

        """
        if street in ("FLOP", "TURN", "RIVER"):
            # Parse the community cards from the hand object's streets dictionary
            m = self.re_board.search(hand.streets[street])
            # Set the community cards in the hand object
            hand.setCommunityCards(street, m.group("CARDS").split(","))

    def readAntes(self, hand: "Hand") -> None:
        """Reads the antes from the hand and adds them to the Hand object.

        Args:
            hand: The Hand object to add the antes to.

        Returns:
            None

        """
        log.debug("reading antes")
        m = self.re_antes.finditer(hand.handText)
        for player in m:
            # Uncomment the following line to enable logging
            log.debug("hand.addAnte(%s,%s)", player.group("PNAME"), player.group("ANTE"))
            hand.addAnte(player.group("PNAME"), self.convertMoneyString("ANTE", player))

    def readBringIn(self, hand: "Hand") -> None:
        """Reads the BringIn information from the hand's handText and adds it to the hand object.

        Args:
            hand (Hand): The Hand object to add the BringIn information to.

        Returns:
            None

        """
        if m := self.re_bring_in.search(hand.handText, re.DOTALL):
            # The BringIn information was found, add it to the hand object.
            hand.addBringIn(m.group("PNAME"), self.convertMoneyString("BRINGIN", m))

    def readBlinds(self, hand: "Hand") -> None:
        """Parses the hand text and extracts the blinds information.

        Args:
            hand: An instance of the Hand class representing the hand being parsed.

        Returns:
            None

        """
        # Flag to keep track of whether the small blind is still live.
        live_blind = True

        # If no bets were returned, set the uncalled bets flag to True.
        if not self.re_return_bet.search(hand.handText):
            hand.setUncalledBets(True)

        # Find all instances of the small blind and add them to the Hand object.
        for a in self.re_post_sb.finditer(hand.handText):
            if live_blind:
                hand.addBlind(
                    a.group("PNAME"),
                    "small blind",
                    self.convertMoneyString("SB", a),
                )
                live_blind = False
            else:
                # Post dead blinds as ante
                hand.addBlind(
                    a.group("PNAME"),
                    "secondsb",
                    self.convertMoneyString("SB", a),
                )

        # Find all instances of the big blind and add them to the Hand object.
        for a in self.re_post_bb.finditer(hand.handText):
            hand.addBlind(
                a.group("PNAME"),
                "big blind",
                self.convertMoneyString("BB", a),
            )

        # Find all instances of both blinds being posted and add them to the Hand object.
        for a in self.re_post_both.finditer(hand.handText):
            sb = Decimal(self.clearMoneyString(a.group("SB")))
            bb = Decimal(self.clearMoneyString(a.group("BB")))
            sbbb = sb + bb
            hand.addBlind(a.group("PNAME"), "both", str(sbbb))

    def readHoleCards(self, hand: "Hand") -> None:
        """Reads the hero's hole cards from the given hand object and adds them to the corresponding streets.

        Args:
            hand (Hand): The hand object containing the streets and player information.

        Returns:
            None

        """
        # Iterate through the streets where hole cards can be found
        for street in ("PREFLOP", "DEAL"):
            # Check if the street is present in the hand object
            if street in list(hand.streets.keys()):
                # Use regex to find hero's cards in the street
                m = self.re_hero_cards.finditer(hand.streets[street])
                # Iterate through each match found
                for found in m:
                    # Save the hero's name
                    hand.hero = found.group("PNAME")
                    # Split the hole cards string into individual cards
                    newcards = found.group("NEWCARDS").split(",")
                    # Add the hole cards to the corresponding street
                    hand.addHoleCards(
                        street,
                        hand.hero,
                        closed=newcards,
                        shown=False,
                        mucked=False,
                        dealt=True,
                    )

    def readAction(self, hand: "Hand", street: str) -> None:
        """Read actions from the hand and update the Hand object.

        Args:
            hand: Hand object representing the current state of the hand.
            street: String representing the current betting round of the hand.
        """
        # Find all the actions in the current street of the hand
        m = self.re_action.finditer(hand.streets[street])

        # Loop through each action and update the Hand object accordingly
        for action in m:
            bet = self.convertMoneyString("BET", action)
            action_type = action.group("ATYPE")

            # If the current action is a fold and not in preflop, add a fold to the Hand object
            if street != "PREFLOP" or action_type != " folds":
                hand.setUncalledBets(False)
            if action_type == " folds":
                hand.addFold(street, action.group("PNAME"))

            # If the current action is a check, add a check to the Hand object
            elif action_type == " checks":
                hand.addCheck(street, action.group("PNAME"))

            # If the current action is a call, add a call to the Hand object
            elif action_type == " calls":
                hand.addCall(street, action.group("PNAME"), bet)

            # If the current action is a raise, add a raise to the Hand object
            elif action_type == " raises":
                hand.setUncalledBets(None)
                hand.addRaiseTo(street, action.group("PNAME"), bet)

            # If the current action is a bet, add a bet to the Hand object
            elif action_type == " bets":
                hand.addBet(street, action.group("PNAME"), bet)

            # If the current action is an all-in, add an all-in to the Hand object
            elif action_type == " is all in":
                hand.addAllIn(street, action.group("PNAME"), bet)

            # If the current action is not one of the above types, log an error
            else:
                log.error(
                    "Unimplemented readAction: '%s' '%s'",
                    action.group("PNAME"),
                    action.group("ATYPE"),
                )

    def readShowdownActions(self, hand: "Hand") -> None:
        """Parses a hand of cards and returns the best possible action to take in a game of poker.

        Args:
            hand (list): A list of cards in the hand.

        Returns:
            str: The best possible action to take.

        """

    def readCollectPot(self, hand: "Hand") -> None:
        """Finds the collect pot for a given hand and adds it to the Hand object.

        Args:
            hand (Hand): The Hand object to which the collect pot will be added.

        Returns:
            None

        """
        # Find all instances of the collect pot in the hand text.
        for m in self.re_collect_pot.finditer(hand.handText):
            # Only consider the collect pot if it is not part of a tournament hand.
            if not re.search(r"Tournament:\s", m.group("PNAME")):
                # Add the collect pot to the Hand object.
                hand.addCollectPot(
                    player=m.group("PNAME"),
                    pot=self.convertMoneyString("POT", m),
                )

    def readShownCards(self, hand: "Hand") -> None:
        """Finds shown cards in a hand text and adds them to the Hand object.

        Args:
            hand: The Hand object to which shown cards will be added.

        Returns:
            None

        """
        # Find shown cards using regular expression.
        for m in self.re_shown_cards.finditer(hand.handText):
            if m.group("CARDS") is not None:
                cards = m.group("CARDS")
                string = m.group("STRING")

                # Check if player showed or mucked cards.
                (shown, mucked) = (False, False)
                if m.group("SHOWED") == "shows":
                    shown = True
                    # Split cards into a list.
                    cards = cards.split(" ")
                elif m.group("SHOWED") == "mucks":
                    mucked = True
                    # Split cards into a list and remove any leading/trailing whitespace.
                    cards = [c.strip() for c in cards.split(",")]

                # Try to add shown cards to the hand.
                try:
                    hand.checkPlayerExists(m.group("PNAME"))
                    player = m.group("PNAME")
                except FpdbParseError:
                    # If the player doesn't exist, replace underscores with spaces in the player name.
                    player = m.group("PNAME").replace("_", " ")

                # Add shown cards to the hand.
                hand.addShownCards(
                    cards=cards,
                    player=player,
                    shown=shown,
                    mucked=mucked,
                    string=string,
                )

    def convertMoneyString(self, currency_type: str, match: Match[str]) -> str:
        """Converts a string of money to a float value.

        Args:
            currency_type: string type of currency (e.g. "USD", "GBP", etc.)
            match: string to be converted

        Returns:
            float value of the money string or "0" if no match found

        """
        if match.group(currency_type):
            # if the match is in the specified currency format, return the cleared money string
            return self.clearMoneyString(match.group(currency_type))
        # if no match found, return "0"
        return "0"

    @staticmethod
    def getTableTitleRe(
        _game_type: str,
        _table_name: str | None = None,
        tournament: str | None = None,
        table_number: str | None = None,
    ) -> str:
        """Generate a regex to match a table title.

        Note: This implementation is specific to tournament tables.

        Args:
            _game_type: The type of game (unused).
            _table_name: The name of the table (unused).
            tournament: The tournament ID.
            table_number: The table number in the tournament.

        Returns:
            A regex string to match the table title.
        """
        log.info(
            "table_name='%s' tournament='%s' table_number='%s'",
            _table_name,
            tournament,
            table_number,
        )
        regex = ""
        log.debug("regex get table cash title: %s", regex)
        if tournament:
            regex = rf"Tournament:\s{tournament}\sBuy\-In\s\w+\s:\sTable\s{table_number}"
            # Tournament: 17106061 Buy-In Freeroll : Table 10 - No Limit Holdem - 15/30
            log.debug("regex get mtt sng expresso cash title: %s", regex)
        log.info("Seals.getTableTitleRe: returns: '%s'", regex)
        return regex

    def readSTP(self, hand: "Hand") -> None:
        """Read STP (sit and go tournament) information from hand.

        Args:
            hand: The Hand object to read STP information from.

        Returns:
            None

        """

    def readSummaryInfo(self, summary_info_list: list) -> None:
        """Read summary information from the provided list.

        Args:
            summary_info_list: List containing summary information to parse.

        Returns:
            None

        """

    def readTourneyResults(self, hand: "Hand") -> None:
        """Read tournament results directly from a hand.

        Args:
            hand: The Hand object to read tournament results from.

        Returns:
            None

        """

    def readOther(self, hand: "Hand") -> None:
        """Read other information from hand that doesn't fit standard categories.

        Args:
            hand: The Hand object to read other information from.

        Returns:
            None

        """
