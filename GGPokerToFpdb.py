"""GGPoker hand history parser for FPDB.

This module provides parsing functionality for GGPoker hand history files.
Handles Hold'em, Omaha, Short Deck and other game types from GGPoker.
"""
#
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

# TODO(dev): straighten out discards for draw games

import datetime
import re
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter

if TYPE_CHECKING:
    from Hand import Hand
from loggingFpdb import get_logger

# GGpoker HH Format
log = get_logger("parser")


class GGPoker(HandHistoryConverter):
    """GGPoker hand history converter.

    Parses GGPoker hand history files and converts them to FPDB format.
    Supports Hold'em, Omaha, Short Deck and other game variations.
    """

    sitename = "GGPoker"
    # Constants
    MIN_HOLDEM_CARDS = 2  # Minimum cards for Hold'em display
    filetype = "text"
    codepage = ("utf8", "cp1252")
    site_id = 27  # Needs to match id entry in Sites database
    sym: ClassVar[dict[str, str]] = {
        "USD": r"\$",
        "T$": "",
        "play": "",
    }  # ADD Euro, Sterling, etc HERE
    substitutions: ClassVar[dict[str, str]] = {
        "LEGAL_ISO": "USD|CNY",  # legal ISO currency codes
        "LS": r"\$|\¥|",  # legal currency symbols - Euro(cp1252, utf-8)
        "PLYR": r"\s?(?P<PNAME>.+?)",
        "CUR": r"(\$|\¥|)",
        "BRKTS": (
            r"(\(button\) |\(small blind\) |\(big blind\) |\(button blind\) |"
            r"\(button\) \(small blind\) |\(small blind/button\) |\(button\) \(big blind\) )?"
        ),
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
        "16.00": ("4.00", "8.00"),
        "16": ("4.00", "8.00"),
        "20.00": ("5.00", "10.00"),
        "20": ("5.00", "10.00"),
        "30.00": ("10.00", "15.00"),
        "30": ("10.00", "15.00"),
        "40.00": ("10.00", "20.00"),
        "40": ("10.00", "20.00"),
        "50.00": ("10.00", "25.00"),
        "50": ("10.00", "25.00"),
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
        "500.00": ("100.00", "250.00"),
        "500": ("100.00", "250.00"),
        "600.00": ("150.00", "300.00"),
        "600": ("150.00", "300.00"),
        "800.00": ("200.00", "400.00"),
        "800": ("200.00", "400.00"),
        "1000.00": ("250.00", "500.00"),
        "1000": ("250.00", "500.00"),
        "2000.00": ("500.00", "1000.00"),
        "2000": ("500.00", "1000.00"),
        "4000.00": ("1000.00", "2000.00"),
        "4000": ("1000.00", "2000.00"),
        "10000.00": ("2500.00", "5000.00"),
        "10000": ("2500.00", "5000.00"),
        "20000.00": ("5000.00", "10000.00"),
        "20000": ("5000.00", "10000.00"),
        "40000.00": ("10000.00", "20000.00"),
        "40000": ("10000.00", "20000.00"),
    }

    limits: ClassVar[dict[str, str]] = {
        "No Limit": "nl",
        "Pot Limit": "pl",
        "Fixed Limit": "fl",
        "Limit": "fl",
        "(NL postflop)": "pn",
    }
    games: ClassVar[dict[str, tuple[str, str]]] = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "ShortDeck": ("hold", "6_holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi/Lo": ("hold", "omahahilo"),
        "PLO": ("hold", "omahahi"),
        "PLO-5": ("hold", "5_omahahi"),
        "PLO-6": ("hold", "6_omahahi"),
    }

    currencies: ClassVar[dict[str, str]] = {"$": "USD", "": "T$", "¥": "CNY"}

    # Poker Hand #TM316262814: Tournament #9364957, WSOP #77: $5,000 No Limit Hold'em Main Event [Flight W],
    # $25M GTD Hold'em No Limit - Level10 (1,000/2,000) - 2020/08/30 15:49:08
    # Poker Hand #TM247771977: Tournament #5259595, Daily Special $250 Hold'em No Limit - Level2 (60/120) -
    # 2020/06/02 19:17:33
    # Static regexes
    re_game_info = re.compile(
        """
          Poker\\sHand\\s\\#[A-Z]{{0,2}}(?P<HID>[0-9]+):\\s+
          (\\{{.*\\}}\\s+)?((?P<TOUR>((Zoom|Rush)\\s)?(Tournament))\\s\\#                # open paren of tournament info
          (?P<TOURNO>\\d+),\\s
          # here's how I plan to use LS
          (?P<TOURNAME>.+?)\\s
          )?
          # close paren of tournament info
          (?P<GAME>Hold\'em|Hold\'em|ShortDeck|Omaha|PLO|Omaha\\sHi/Lo|PLO\\-(5|6))\\s
          (?P<LIMIT>No\\sLimit|Fixed\\sLimit|Limit|Pot\\sLimit|\\(NL\\spostflop\\))?,?\\s*
          (-\\s)?
          (?P<SHOOTOUT>Match.*,\\s)?
          (Level(?P<LEVEL>[IVXLC\\d]+)\\s?)?
          \\(?                            # open paren of the stakes
          (?P<CURRENCY>{LS}|)?
          (ante\\s\\d+,\\s)?
          ((?P<SB>[,.0-9]+)/({LS})?(?P<BB>[,.0-9]+)|(?P<BUB>[,.0-9]+))
          (?P<CAP>\\s-\\s[{LS}]?(?P<CAPAMT>[,.0-9]+)\\sCap\\s-\\s)?        # Optional Cap part
          \\s?(?P<ISO>{LEGAL_ISO})?
          \\)                        # close paren of the stakes
          (?P<BLAH2>\\s\\[AAMS\\sID:\\s[A-Z0-9]+\\])?         # AAMS ID: in .it HH's
          \\s-\\s
          (?P<DATETIME>.*$)
        """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_player_info = re.compile(
        r"""
          ^\s?Seat\s(?P<SEAT>[0-9]+):\s
          (?P<PNAME>.*)\s
          \(({LS})?(?P<CASH>[,.0-9]+)\sin\schips
          (,\s({LS})?(?P<BOUNTY>[,.0-9]+)\sbounty)?
          \)
          (?P<SITOUT>\sis\ssitting\sout)?""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_hand_info = re.compile(
        """
          ^\\s?Table\\s(ID\\s)?\'(?P<TABLE>.+?)\'\\s
          ((?P<MAX>\\d+)-max\\s)?
          (?P<PLAY>\\(Play\\sMoney\\)\\s)?
          (Seat\\s\\#(?P<BUTTON>\\d+)\\sis\\sthe\\sbutton)?""",
        re.MULTILINE | re.VERBOSE,
    )

    re_identify = re.compile(r"Poker\sHand\s\#[A-Z]{0,2}?\d+:")
    re_split_hands = re.compile("(?:\\s?\n){2,}")
    re_tail_split_hands = re.compile("(\n\n\n+)")
    re_button = re.compile(r"Seat #(?P<BUTTON>\d+) is the button", re.MULTILINE)
    re_board = re.compile(r"\[(?P<CARDS>.+)\]")
    re_board2 = re.compile(r"\[(?P<C1>\S\S)\] \[(\S\S)?(?P<C2>\S\S) (?P<C3>\S\S)\]")
    re_board3 = re.compile(
        r"Board\s\[(?P<FLOP>\S\S \S\S \S\S) (?P<TURN>\S\S) (?P<RIVER>\S\S)\]",
    )
    re_date_time1 = re.compile(
        r"""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""",
        re.MULTILINE,
    )
    re_date_time2 = re.compile(
        r"""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+)""",
        re.MULTILINE,
    )

    # These used to be compiled per player, but regression tests say
    # we don't have to, and it makes life faster.
    re_post_sb = re.compile(
        r"^{PLYR}: posts small blind {CUR}(?P<SB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_post_bb = re.compile(
        r"^{PLYR}: posts big blind {CUR}(?P<BB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_post_bub = re.compile(
        r"^{PLYR}: posts button blind {CUR}(?P<BUB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_antes = re.compile(
        r"^{PLYR}: posts the ante {CUR}(?P<ANTE>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_bring_in = re.compile(
        r"^{PLYR}: brings[- ]in( low|) for {CUR}(?P<BRINGIN>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_post_missed = re.compile(
        r"^{PLYR}: posts missed blind {CUR}(?P<SBBB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_post_straddle = re.compile(
        r"^{PLYR}: straddle {CUR}(?P<STRADDLE>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_action = re.compile(
        r"""
                        ^{PLYR}:(?P<ATYPE>\sbets|\schecks|\sraises|\scalls|\sfolds|\sdiscards|\sstands\spat|\sChooses\sto\sEV\sCashout|\sReceives\sCashout)
                        (\s{CUR}(?P<BET>[,.\d]+))?(\sto\s{CUR}(?P<BETTO>[,.\d]+))?  # the number discarded goes in <BET>
                        \s*(and\sis\sall.in)?
                        (and\shas\sreached\sthe\s[{CUR}\d\.,]+\scap)?
                        (\son|\scards?)?
                        (\s\(disconnect\))?
                        (\s\[(?P<CARDS>.+?)\])?\s*$""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    re_showdown_action = re.compile(
        r"^{}: shows \[(?P<CARDS>.*)\]".format(substitutions["PLYR"]), re.MULTILINE,
    )
    re_sits_out = re.compile("^{} sits out".format(substitutions["PLYR"]), re.MULTILINE)
    re_collect_pot = re.compile(
        r"Seat (?P<SEAT>[0-9]+): {PLYR} {BRKTS}(collected|showed \[.*\] and (won|collected)) "
        r"\(?{CUR}(?P<POT>[,.\d]+)\)?(, mucked| with.*|)".format(**substitutions),
        re.MULTILINE,
    )
    # Vinsand88 cashed out the hand for $2.19 | Cash Out Fee $0.02
    re_collect_pot2 = re.compile(
        r"^{PLYR} collected {CUR}(?P<POT>[,.\d]+)".format(**substitutions), re.MULTILINE,
    )
    re_collect_pot3 = re.compile(
        r"^{PLYR}: Receives Cashout \({CUR}(?P<POT>[,.\d]+)\)".format(**substitutions),
        re.MULTILINE,
    )
    re_collect_pot4 = re.compile(
        r"^{PLYR}: Pays Cashout Risk \({CUR}(?P<POT>[,.\d]+)\)".format(**substitutions),
        re.MULTILINE,
    )
    re_cashed_out = re.compile(r"(Chooses\sto\sEV\sCashout|Receives\sCashout)")
    re_winning_rank_one = re.compile(
        r"^{PLYR} wins the tournament and receives {CUR}(?P<AMT>[,\.0-9]+) - congratulations!$".format(**substitutions),
        re.MULTILINE,
    )
    re_winning_rank_other = re.compile(
        r"^{PLYR} finished the tournament in (?P<RANK>[0-9]+)(st|nd|rd|th) place "
        r"and received {CUR}(?P<AMT>[,.0-9]+)\.$".format(**substitutions),
        re.MULTILINE,
    )
    re_rank_other = re.compile(
        "^{PLYR} finished the tournament in (?P<RANK>[0-9]+)(st|nd|rd|th) place$".format(**substitutions),
        re.MULTILINE,
    )
    re_cancelled = re.compile(r"Hand\scancelled", re.MULTILINE)
    re_uncalled = re.compile(
        r"Uncalled bet \({CUR}(?P<BET>[,.\d]+)\) returned to".format(**substitutions),
        re.MULTILINE,
    )
    # APTEM-89 wins the $0.27 bounty for eliminating Hero
    # ChazDazzle wins the 22000 bounty for eliminating berkovich609
    # JKuzja, vecenta split the $50 bounty for eliminating ODYSSES
    re_bounty = re.compile(
        r"^{PLYR} (?P<SPLIT>split|wins) the {CUR}(?P<AMT>[,\.0-9]+) bounty "
        r"for eliminating (?P<ELIMINATED>.+?)$".format(**substitutions),
        re.MULTILINE,
    )
    # Amsterdam71 wins $19.90 for eliminating MuKoJla and their own bounty increases by $19.89 to $155.32
    # Amsterdam71 wins $4.60 for splitting the elimination of Frimble11
    # and their own bounty increases by $4.59 to $41.32
    # Amsterdam71 wins the tournament and receives $230.36 - congratulations!
    re_progressive = re.compile(
        r"""
                        ^{PLYR}\swins\s{CUR}(?P<AMT>[,\.0-9]+)\s
                        for\s(splitting\sthe\selimination\sof|eliminating)\s(?P<ELIMINATED>.+?)\s
                        and\stheir\sown\sbounty\sincreases\sby\s{CUR}(?P<INCREASE>[\.0-9]+)\sto\s{CUR}(?P<ENDAMT>[\.0-9]+)$""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )
    re_rake = re.compile(
        r"""Total\s+pot\s+{CUR}(?P<POT>[,\.0-9]+)(\s+\|\s+Rake\s+{CUR}(?P<RAKE>[,\.0-9]+))?""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_stp = re.compile(
        r"""
                        Cash\sDrop\sto\sPot\s:\stotal\s{CUR}(?P<AMOUNT>[,\.0-9]+)""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    def compilePlayerRegexs(self, hand: "Hand") -> None:
        """Compile player-specific regex patterns for the hand."""
        players = {player[1] for player in hand.players}
        if not players <= self.compiledPlayers:  # x <= y means 'x is subset of y'
            self.compiledPlayers = players
            player_re = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"
            subst = {
                "PLYR": player_re,
                "BRKTS": (r"(\(button\) |\(small blind\) |\(big blind\) |"
                         r"\(button\) \(small blind\) |\(button\) \(big blind\) )?"),
                "CUR": "(\\$|\xe2\x82\xac|\u20ac||\\£|)",
            }
            self.re_HeroCards = re.compile(
                r"^Dealt to {PLYR}(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(**subst),
                re.MULTILINE,
            )
            # Regex to detect all players dealt cards (even if cards are hidden)
            self.re_dealt_cards = re.compile(
                r"^Dealt to {PLYR}".format(**subst),
                re.MULTILINE,
            )
            self.re_ShownCards = re.compile(
                r"^Seat (?P<SEAT>[0-9]+): {PLYR} {BRKTS}(?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]"
                r"( and (lost|(won|collected) \({CUR}(?P<POT>[,\.\d]+)\)) with (?P<STRING>.+?)"
                r"(,\sand\s(won\s\({CUR}[\.\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?$".format(**subst),
                re.MULTILINE,
            )

    def readSupportedGames(self) -> list[list[str]]:
        """Return list of supported game types."""
        return [
            ["ring", "hold", "nl"],
            ["ring", "hold", "pl"],
            ["ring", "hold", "fl"],
            ["ring", "hold", "pn"],
            ["ring", "stud", "fl"],
            ["ring", "draw", "fl"],
            ["ring", "draw", "pl"],
            ["ring", "draw", "nl"],
            ["tour", "hold", "nl"],
            ["tour", "hold", "pl"],
            ["tour", "hold", "fl"],
            ["tour", "hold", "pn"],
            ["tour", "stud", "fl"],
            ["tour", "draw", "fl"],
            ["tour", "draw", "pl"],
            ["tour", "draw", "nl"],
        ]

    def _parse_basic_game_info(self, mg: dict) -> dict[str, str]:
        """Parse basic game information from match groups."""
        info = {}

        # Limit type
        info["limitType"] = self.limits.get(mg.get("LIMIT"), "pl")

        # Game base and category
        if "GAME" in mg:
            info["base"], info["category"] = self.games[mg["GAME"]]

        # Blinds
        if mg.get("SB"):
            info["sb"] = self.clearMoneyString(mg["SB"])
        if mg.get("BB"):
            info["bb"] = self.clearMoneyString(mg["BB"])
        if mg.get("BUB"):
            info["sb"] = "0"
            info["bb"] = self.clearMoneyString(mg["BUB"])

        return info

    def _parse_game_type_and_currency(self, mg: dict) -> dict[str, str]:
        """Parse game type and currency information."""
        info = {}

        # Currency
        if "CURRENCY" in mg:
            info["currency"] = self.currencies[mg["CURRENCY"]]

        # Buyin type
        info["buyinType"] = "cap" if mg.get("CAP") else "regular"

        # Split games
        info["split"] = mg.get("SPLIT") == "Split"

        # Game type (ring vs tournament)
        if mg.get("TOURNO") is None:
            info["type"] = "ring"
        else:
            info["type"] = "tour"
            if "ZOOM" in mg.get("TOUR", ""):
                info["fast"] = True

        return info

    def _adjust_fixed_limit_blinds(self, info: dict, mg: dict, hand_text: str) -> None:
        """Adjust blinds for fixed limit games."""
        if info["limitType"] != "fl" or not info.get("bb"):
            return

        if info["type"] == "ring":
            try:
                bb_key = self.clearMoneyString(mg["BB"])
                info["sb"] = self.Lim_Blinds[bb_key][0]
                info["bb"] = self.Lim_Blinds[bb_key][1]
            except KeyError as e:
                tmp = hand_text[0:200]
                log.exception("Lim_Blinds has no lookup for '%s' - '%s'", mg["BB"], tmp)
                raise FpdbParseError from e
        else:
            sb_decimal = Decimal(self.clearMoneyString(mg["SB"]))
            info["sb"] = str((sb_decimal / 2).quantize(Decimal("0.01")))
            info["bb"] = str(sb_decimal.quantize(Decimal("0.01")))

    def determineGameType(self, hand_text: str) -> dict[str, str]:
        """Parse hand text to determine game type information."""
        m = self.re_game_info.search(hand_text)
        if not m:
            tmp = hand_text[0:200]
            log.error("determineGameType not found: '%s'", tmp)
            raise FpdbParseError

        mg = m.groupdict()

        # Parse different aspects of game info
        info = {}
        info.update(self._parse_basic_game_info(mg))
        info.update(self._parse_game_type_and_currency(mg))

        # Handle special currency case
        if info.get("currency") in ("T$", None) and info["type"] == "ring":
            info["currency"] = "play"

        # Adjust fixed limit blinds
        self._adjust_fixed_limit_blinds(info, mg, hand_text)

        return info

    def _parse_datetime(self, hand: "Hand", datetime_str: str) -> None:
        """Parse and set hand start time from datetime string."""
        # 2008/11/12 10:00:48 CET [2008/11/12 4:00:48 ET]
        # (both dates are parsed so ET date overrides the other)
        datetimestr = "2000/01/01 00:00:00"  # default used if time not found
        m1 = self.re_date_time1.finditer(datetime_str)
        for a in m1:
            datetimestr = "{}/{}/{} {}:{}:{}".format(
                a.group("Y"), a.group("M"), a.group("D"),
                a.group("H"), a.group("MIN"), a.group("S"),
            )
        hand.startTime = datetime.datetime.strptime(  # noqa: DTZ007
            datetimestr, "%Y/%m/%d %H:%M:%S",
        )
        hand.startTime = HandHistoryConverter.changeTimezone(hand.startTime, "ET", "UTC")

    def _detect_currency(self, buyin_str: str, hand: "Hand") -> None:
        """Detect and set currency from buyin string."""
        currency_mapping = {
            "$": "USD", "£": "GBP", "€": "EUR", "₹": "INR", "¥": "CNY",
        }

        for symbol, currency in currency_mapping.items():
            if symbol in buyin_str:
                hand.buyinCurrency = currency
                return

        if "FPP" in buyin_str or "SC" in buyin_str:
            hand.buyinCurrency = "PSFP"
        elif re.match("^[0-9+]*$", buyin_str.strip()):
            hand.buyinCurrency = "play"
        else:
            log.error("Failed to detect currency. Hand ID: %s: '%s'", hand.handid, buyin_str)
            raise FpdbParseError

    def _process_buyin_info(self, hand: "Hand", info: dict) -> None:
        """Process tournament buyin information."""
        buyin_str = info["BUYIN"].strip()

        if buyin_str == "Freeroll":
            hand.buyin = hand.fee = 0
            hand.buyinCurrency = "FREE"
            return
        if buyin_str == "":
            hand.buyin = hand.fee = 0
            hand.buyinCurrency = "NA"
            return

        self._detect_currency(buyin_str, hand)

        # Remove currency symbols
        currency_chars = str.maketrans("", "", "$€£FPPSC₹")
        info["BIAMT"] = info["BIAMT"].translate(currency_chars)

        if hand.buyinCurrency != "PSFP":
            self._handle_bounty_and_fees(hand, info)
        else:
            hand.buyin = int(100 * Decimal(info["BIAMT"]))
            hand.fee = 0

    def _handle_bounty_and_fees(self, hand: "Hand", info: dict) -> None:
        """Handle bounty tournaments and fee calculation."""
        if info["BOUNTY"] is not None:
            # Swap BOUNTY and BIRAKE values for bounty tournaments
            info["BOUNTY"], info["BIRAKE"] = info["BIRAKE"], info["BOUNTY"]
            info["BOUNTY"] = info["BOUNTY"].strip("$€£₹")
            hand.koBounty = int(100 * Decimal(info["BOUNTY"]))
            hand.isKO = True
        else:
            hand.isKO = False

        info["BIRAKE"] = info["BIRAKE"].strip("$€£₹")
        hand.buyin = int(100 * Decimal(info["BIAMT"])) + hand.koBounty
        hand.fee = int(100 * Decimal(info["BIRAKE"]))

    def readHandInfo(self, hand: "Hand") -> None:
        """Read and parse hand information from hand text."""
        self._validate_hand_summary(hand)
        info = self._extract_hand_info(hand)
        self._process_hand_info(hand, info)
        self._check_special_conditions(hand)

    def _validate_hand_summary(self, hand: "Hand") -> None:
        """Validate that hand has proper summary structure."""
        if hand.handText.count("*** SUMMARY ***") != 1:
            msg = "Hand is not cleanly split into pre and post Summary"
            raise FpdbHandPartial(msg)

    def _extract_hand_info(self, hand: "Hand") -> dict[str, str]:
        """Extract hand information using regex patterns."""
        info = {}
        m = self.re_hand_info.search(hand.handText, re.DOTALL)
        m2 = self.re_game_info.search(hand.handText)
        if m is None or m2 is None:
            tmp = hand.handText[0:200]
            log.error("readHandInfo not found: '%s'", tmp)
            raise FpdbParseError

        info.update(m.groupdict())
        info.update(m2.groupdict())
        return info

    def _process_hand_info(self, hand: "Hand", info: dict[str, str]) -> None:
        """Process extracted hand information into hand object."""
        for key in info:
            if key == "DATETIME":
                self._parse_datetime(hand, info[key])
            elif key == "HID":
                hand.handid = info[key]
            elif key == "TOURNO":
                hand.tourNo = info[key]
            elif key == "BUYIN" and hand.tourNo is not None:
                self._process_buyin_info(hand, info)
            elif key == "LEVEL":
                hand.level = info[key]
            elif key == "SHOOTOUT" and info[key] is not None:
                hand.isShootout = True
            elif key == "MAX" and info[key] is not None:
                hand.maxseats = int(info[key])

        # Process rake and pot information from summary
        self._process_rake_info(hand)

    def _process_rake_info(self, hand: "Hand") -> None:
        """Process rake and pot information from summary section."""
        # Extract rake and pot information from summary
        rake_match = self.re_rake.search(hand.handText)
        if rake_match:
            pot_total = self.clearMoneyString(rake_match.group("POT"))
            rake_amount = rake_match.group("RAKE")

            # Set rake if found in hand history (rake group is optional)
            if rake_amount:
                hand.rake = Decimal(self.clearMoneyString(rake_amount))

            # Store total pot for validation (this helps with pot calculation)
            if pot_total:
                hand.totalpot = Decimal(pot_total)

    def _check_special_conditions(self, hand: "Hand") -> None:
        """Check for special game conditions."""
        if "Zoom" in self.in_path or "Rush" in self.in_path:
            hand.gametype["fast"], hand.isFast = True, True

        if self.re_cancelled.search(hand.handText):
            msg = f"Hand '{hand.handid}' was cancelled."
            raise FpdbHandPartial(msg)

    def readButton(self, hand: "Hand") -> None:
        """Read and set button position from hand text."""
        m = self.re_button.search(hand.handText)
        if m:
            hand.buttonpos = int(m.group("BUTTON"))
        else:
            hand.buttonpos = 0

    def readPlayerStacks(self, hand: "Hand") -> None:
        """Read and set player stack information from hand text."""
        log.debug("readPlayerStacks")
        pre, _post = hand.handText.split("*** SUMMARY ***")
        m = self.re_player_info.finditer(pre)
        for a in m:
            hand.addPlayer(
                int(a.group("SEAT")),
                a.group("PNAME"),
                self.clearMoneyString(a.group("CASH")),
            )

    def markStreets(self, hand: "Hand") -> None:
        """Mark different streets in the hand text."""
        # PREFLOP = ** Dealing down cards **
        # This re fails if,  say, river is missing; then we don't get the ** that starts the river.
        if hand.gametype["base"] in ("hold"):
            re.search(
                r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>(.+(?P<FLOPET>\[\S\S\]))?.+(?=\*\*\* (FIRST\s)?FLOP \*\*\*)|.+)"
                r"(\*\*\* FLOP \*\*\*(?P<FLOP>  ?(\[\S\S\] )?\[(\S\S ?)?\S\S \S\S\]"
                r".+(?=\*\*\* (FIRST\s)?TURN \*\*\*)|.+))?"
                r"(\*\*\* TURN \*\*\* \[\S\S \S\S \S\S] (?P<TURN>\[\S\S\].+(?=\*\*\* (FIRST\s)?RIVER \*\*\*)|.+))?"
                r"(\*\*\* RIVER \*\*\* \[\S\S \S\S \S\S \S\S] (?P<RIVER>\[\S\S\].+))?"
                r"(\*\*\* FIRST FLOP \*\*\*(?P<FLOP1>  ?(\[\S\S\] )?\[\S\S \S\S \S\S\]"
                r".+(?=\*\*\* FIRST TURN \*\*\*)|.+))?"
                r"(\*\*\* FIRST TURN \*\*\* \[\S\S \S\S \S\S] (?P<TURN1>\[\S\S\].+(?=\*\*\* FIRST RIVER \*\*\*)|.+))?"
                r"(\*\*\* FIRST RIVER \*\*\* \[\S\S \S\S \S\S \S\S] (?P<RIVER1>\[\S\S\]"
                r".+?(?=\*\*\* SECOND (FLOP|TURN|RIVER) \*\*\*)|.+))?"
                r"(\*\*\* SECOND FLOP \*\*\*(?P<FLOP2>  ?(\[\S\S\] )?\[\S\S \S\S \S\S\]"
                r".+(?=\*\*\* SECOND TURN \*\*\*)|.+))?"
                r"(\*\*\* SECOND TURN \*\*\* \[\S\S \S\S \S\S] (?P<TURN2>\[\S\S\].+(?=\*\*\* SECOND RIVER \*\*\*)|.+))?"
                r"(\*\*\* SECOND RIVER \*\*\* \[\S\S \S\S \S\S \S\S] "
                r"(?P<RIVER2>\[\S\S].+?(?=\*\*\* THIRD (FLOP|TURN|RIVER) \*\*\*)|\.+))?"
                r"(\*\*\* THIRD FLOP \*\*\*(?P<FLOP3>  ?(\[\S\S] )?"
                r"\[\S\S \S\S \S\S].+(?=\*\*\* THIRD TURN \*\*\*)|\.+))?"
                r"(\*\*\* THIRD TURN \*\*\* \[\S\S \S\S \S\S] (?P<TURN3>\[\S\S\].+(?=\*\*\* THIRD RIVER \*\*\*)|.+))?"
                r"(\*\*\* THIRD RIVER \*\*\* \[\S\S \S\S \S\S \S\S] (?P<RIVER3>\[\S\S\].+))?",
                hand.handText,
                re.DOTALL,
            )

            if m1 := self.re_board3.search(hand.handText):
                hand.streets.update(
                    {
                        "FLOP": "[{}]".format(m1.group("FLOP")),
                        "TURN": "[{}]".format(m1.group("TURN")),
                        "RIVER": "[{}]".format(m1.group("RIVER")),
                    },
                )

    def readCommunityCards(
        self, hand: "Hand", street: str,
    ) -> None:  # street has been matched by markStreets, so exists in this hand
        """Read and set community cards for a given street."""
        if (
            street != "FLOPET" or hand.streets.get("FLOP") is None
        ):  # a list of streets which get dealt community cards (i.e. all but PREFLOP)
            m = self.re_board.search(hand.streets[street])
            hand.setCommunityCards(street, m.group("CARDS").split()) if m else None

    def readSTP(self, hand: "Hand") -> None:
        """Read straight to play information from hand text."""
        log.debug("readSTP")
        m = self.re_stp.search(hand.handText)
        if m:
            hand.tourneyTypeId = 0

    def readAntes(self, hand: "Hand") -> None:
        """Read and add ante information from hand text."""
        log.debug("readAntes")
        m = self.re_antes.finditer(hand.handText)
        for player in m:
            hand.addAnte(player.group("PNAME"), self.clearMoneyString(player.group("ANTE")))

    def readBringIn(self, hand: "Hand") -> None:
        """Read and add bring-in information from hand text."""
        m = self.re_bring_in.search(hand.handText, re.DOTALL)
        if m:
            hand.addBringIn(m.group("PNAME"), self.clearMoneyString(m.group("BRINGIN")))

    def readBlinds(self, hand: "Hand") -> None:
        """Read and add blind information from hand text."""
        live_blind, straddles = True, {}
        for a in self.re_post_sb.finditer(hand.handText):
            if live_blind and a.group("PNAME") not in straddles:
                hand.addBlind(a.group("PNAME"), "small blind", self.clearMoneyString(a.group("SB")))
                live_blind = False
            else:
                # Post dead blinds as ante
                hand.addBlind(a.group("PNAME"), "secondsb", self.clearMoneyString(a.group("SB")))

        for a in self.re_post_missed.finditer(hand.handText):
            hand.addBlind(a.group("PNAME"), "secondsb", self.clearMoneyString(a.group("SBBB")))

        for a in self.re_post_straddle.finditer(hand.handText):
            hand.addBlind(a.group("PNAME"), "straddle", self.clearMoneyString(a.group("STRADDLE")))
            straddles[a.group("PNAME")] = True

        live_blind = True

        for _a in self.re_post_bb.finditer(hand.handText):
            live_blind = False

        for a in self.re_post_bub.finditer(hand.handText):
            if live_blind:
                hand.addBlind(a.group("PNAME"), "button blind", self.clearMoneyString(a.group("BUB")))
            else:
                hand.addBlind(a.group("PNAME"), "secondsb", self.clearMoneyString(a.group("BUB")))

    def readHoleCards(self, hand: "Hand") -> None:
        """Read and set hole cards for players from hand text."""
        # First, mark all players who were dealt cards (even if hidden)
        self._mark_dealt_players(hand)

        self._process_initial_streets(hand)
        self._process_remaining_streets(hand)
        self._fix_draw_games(hand)

    def _mark_dealt_players(self, hand: "Hand") -> None:
        """Mark all players who were dealt cards (even if cards are hidden)."""
        # Find all "Dealt to" lines and mark those players as dealt
        for m in self.re_dealt_cards.finditer(hand.handText):
            player_name = m.group("PNAME")
            # Mark player as dealt by adding to the dealt set
            # Don't add empty cards as it causes issues with holecards processing
            hand.dealt.add(player_name)

    def _process_initial_streets(self, hand: "Hand") -> None:
        """Process PREFLOP and DEAL streets for hero cards."""
        for street in ("PREFLOP", "DEAL"):
            if street in hand.streets:
                self._process_hero_cards_for_street(hand, street)

    def _process_remaining_streets(self, hand: "Hand") -> None:
        """Process all other streets for hole cards."""
        for street, text in hand.streets.items():
            if not text or street in ("PREFLOP", "DEAL"):
                continue  # already done these
            self._process_hero_cards_for_street(hand, street)

    def _process_hero_cards_for_street(self, hand: "Hand", street: str) -> None:
        """Process hero cards for a specific street."""
        m = self.re_HeroCards.finditer(hand.streets[street])
        for found in m:
            player = found.group("PNAME")
            newcards = found.group("NEWCARDS").split(" ")
            oldcards = [] if found.group("OLDCARDS") is None else found.group("OLDCARDS").split(" ")

            hand.hero = player
            self._add_hole_cards_by_game_type(hand, street, player, newcards, oldcards)

    def _add_hole_cards_by_game_type(
        self, hand: "Hand", street: str, player: str, newcards: list[str], oldcards: list[str],
    ) -> None:
        """Add hole cards based on game type and street."""
        stud_initial_cards = 3

        if street == "THIRD" and len(newcards) == stud_initial_cards:
            # Hero in stud game
            hand.addHoleCards(street, player, closed=newcards, shown=False, mucked=False, dealt=True)
        elif (street == "PREFLOP" and hand.gametype["category"] == "holdem") or street == "DEAL":
            if hand.gametype["category"] in ("studhi", "studhilo") and street == "DEAL":
                hand.addHoleCards(
                    street, player, closed=oldcards, open=newcards,
                    shown=False, mucked=False, dealt=True,
                )
            else:
                hand.addHoleCards(street, player, closed=newcards, shown=False, mucked=False, dealt=True)

    def _fix_draw_games(self, hand: "Hand") -> None:
        """Fix draw games by inserting DRAW marker."""
        if hand.gametype["category"] in ("27_1draw", "fivedraw"):
            # isolate the first discard/stand pat line (thanks Carl for the regex)
            discard_split = re.split(
                r"(?:(.+(?: stands pat|: discards).+))", hand.handText, maxsplit=0, flags=re.DOTALL,
            )
            if len(hand.handText) != len(discard_split[0]):
                # DRAW street found, reassemble, with DRAW marker added
                discard_split[0] += "*** DRAW ***"
                hand.handText = "".join(discard_split)

    def readAction(self, hand: "Hand", street: str) -> None:
        """Read and parse player actions for a given street."""
        s = street + "2" if hand.gametype["split"] and street in hand.communityStreets else street
        m = self.re_action.finditer(hand.streets[s])
        for action in m:
            player_name = action.group("PNAME")
            amount = self.clearMoneyString(action.group("BET")) if action.group("BET") else None
            action_type = action.group("ATYPE")

            if action_type == "raises":
                # Only some sites provide the target amount for raises
                hand.addRaiseBy(street, player_name, amount)
            elif action_type == "calls":
                hand.addCall(street, player_name, amount)
            elif action_type == "bets":
                hand.addBet(street, player_name, amount)
            elif action_type == "folds":
                hand.addFold(street, player_name)
            elif action_type == "checks":
                hand.addCheck(street, player_name)
            elif action_type == "discards":
                hand.addDiscard(street, player_name, action.group("BET").split(" "), action.group("DISCARDED"))
            elif action_type == "stands pat":
                hand.addStandsPat(street, player_name, action.group("CARDS"))
            elif action_type in ("shows", "shows down"):
                hand.addShownCards(
                    cards=action.group("CARDS").split(" "),
                    player=player_name,
                    shown=True,
                    mucked=False,
                    string=action.group("STRING"),
                )

    def readShowdownActions(self, hand: "Hand") -> bool:
        """Read and parse showdown actions from hand text."""
        for shows in self.re_showdown_action.finditer(hand.handText):
            cards = shows.group("CARDS")
            cards = [c.strip() for c in cards.split(" ")]
            if (
                hand.gametype["category"] in ("holdem")
                and len(cards) > self.MIN_HOLDEM_CARDS
                and hand.gametype["base"] == "hold"
            ):
                hand.addShownCards(cards=cards[0:2], player=shows.group("PNAME"), shown=True, mucked=False)

        for shows in self.re_ShownCards.finditer(hand.handText):
            if shows.group("CARDS") is not None:
                cards = shows.group("CARDS")
                cards = [c.strip() for c in cards.split(" ")]

                (
                    shown,
                    mucked,
                ) = (
                    (True, False) if shows.group("SHOWED") == "showed" else (False, True)
                )

                if (
                    hand.gametype["category"] in ("holdem")
                    and len(cards) > self.MIN_HOLDEM_CARDS
                    and hand.gametype["base"] == "hold"
                ):
                    hand.addShownCards(cards=cards[0:2], player=shows.group("PNAME"), shown=shown, mucked=mucked)
                elif len(cards) > 0:
                    hand.addShownCards(cards=cards, player=shows.group("PNAME"), shown=shown, mucked=mucked)

                if (shows.group("STRING") is not None
                    and hand.gametype["category"] in ("holdem", "omahahi", "omahahilo")
                    and len(cards) > 0):
                        hand.addShownCards(
                            cards=cards,
                            player=shows.group("PNAME"),
                            shown=shown,
                            mucked=mucked,
                            string=shows.group("STRING"),
                        )

        if self.re_bounty.search(hand.handText) is None:
            m = self.re_winning_rank_one.search(hand.handText)
            if m:
                hand.addShownCards(
                    cards=[],
                    player=m.group("PNAME"),
                    shown=False,
                    mucked=False,
                    string="Tournament Winner",
                )
        return True

    def readTourneyResults(self, hand: "Hand") -> None:
        """Reads knockout bounties and add them to the koCounts dict."""
        if self.re_bounty.search(hand.handText) is None:
            return

        ko_amounts = {}
        for a in self.re_progressive.finditer(hand.handText):
            if a.group("PNAME") not in ko_amounts:
                ko_amounts[a.group("PNAME")] = 0
            ko_amounts[a.group("PNAME")] += int(100 * Decimal(a.group("AMT")))

        if ko_amounts:
            hand.koCounts.update(ko_amounts)

        ko_amounts = {}
        for a in self.re_bounty.finditer(hand.handText):
            if a.group("PNAME") not in ko_amounts:
                ko_amounts[a.group("PNAME")] = 0
            if a.group("SPLIT") == "split":
                ko_amounts[a.group("PNAME")] += int(50 * Decimal(a.group("AMT")))
            else:
                ko_amounts[a.group("PNAME")] += int(100 * Decimal(a.group("AMT")))

        if ko_amounts:
            hand.koCounts.update(ko_amounts)

    def readCollectPot(self, hand: "Hand") -> None:
        """Read and parse pot collection information from hand text."""
        i = 0
        pre, post = hand.handText.split("*** SUMMARY ***")
        hand.cashedOut = self.re_cashed_out.search(pre) is not None

        if hand.runItTimes == 0 and hand.cashedOut is False:
            for m in self.re_collect_pot.finditer(post):
                pot = self.clearMoneyString(m.group("POT"))
                hand.addCollectPot(player=m.group("PNAME"), pot=pot)
                i += 1
        if i == 0:
            # Handle regular pot collections only - ignore cashouts for pot accounting
            # Cashouts are separate transactions that don't affect the main pot distribution
            for m in self.re_collect_pot2.finditer(pre):
                player = m.group("PNAME")
                pot = self.clearMoneyString(m.group("POT"))
                hand.addCollectPot(player=player, pot=pot)

    def readOther(self, hand: "Hand") -> None:
        """Read other information from hand text."""

    @staticmethod
    def getTableTitleRe(
        type_: str,
        table_name: str | None = None,
        tournament: str | None = None,
        table_number: str | None = None,
    ) -> str:
        """Returns string to search in windows titles."""
        regex = re.escape(str(table_name))
        if type_ == "tour":
            regex = (
                re.escape(str(tournament))
                + ".* (Table|Tisch) "
                + re.escape(str(table_number))
            )
        log.info(
            "table_name='%s' tournament='%s' table_number='%s'",
            table_name, tournament, table_number,
        )
        log.info("returns: '%s'", regex)
        return regex

    def readSummaryInfo(self, summary_info_list: list) -> bool:  # noqa: ARG002
        """Read summary info from tournament summary."""
        log.info("enter method readSummaryInfo.")
        log.debug("Method readSummaryInfo non implemented.")
        return True

    def readShownCards(self, hand: "Hand") -> None:
        """Read shown cards from hand text."""
        for m in self.re_ShownCards.finditer(hand.handText):
            if m.group("CARDS") is not None:
                cards = m.group("CARDS")
                cards = cards.split(" ")  # needs to be a list, not a set--stud needs the order
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
