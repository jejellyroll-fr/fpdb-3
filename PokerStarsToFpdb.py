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

"""PokerStars hand history converter for FPDB.

This module provides functionality to parse PokerStars hand history files
and convert them into FPDB database format. It supports multiple PokerStars
skins including .COM, .FR, .IT, .ES, .PT, .EU, and .DE variants.

The converter handles various game types including Hold'em, Omaha, Stud,
Draw games, and tournaments across different betting structures.
"""

# TODO(@fpdb): straighten out discards for draw games

import datetime
import re
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger

if TYPE_CHECKING:
    from Hand import Hand

# PokerStars HH Format
log = get_logger("pokerstars_parser")

# Site ID constants
SITE_POKERSTARS_COM = 32
SITE_POKERSTARS_FR = 33
SITE_POKERSTARS_IT = 34
SITE_POKERSTARS_ES = 35
SITE_POKERSTARS_PT = 36
SITE_POKERSTARS_EU = 37
SITE_POKERSTARS_DE = 130
SITE_BOVADA = 19
SITE_MERGE = 26
STUD_HOLE_CARDS_COUNT = 3

# PokerStars skin ID mapping
POKERSTARS_SKIN_IDS = {
    "PokerStars.COM": SITE_POKERSTARS_COM,
    "PokerStars.FR": SITE_POKERSTARS_FR,
    "PokerStars.IT": SITE_POKERSTARS_IT,
    "PokerStars.ES": SITE_POKERSTARS_ES,
    "PokerStars.PT": SITE_POKERSTARS_PT,
    "PokerStars.EU": SITE_POKERSTARS_EU,
    "PokerStars.DE": SITE_POKERSTARS_DE,
}

# Path patterns for skin detection
POKERSTARS_PATH_PATTERNS = [
    ("pokerstars.fr", "PokerStars.FR"),
    ("pokerstars.it", "PokerStars.IT"),
    ("pokerstars.es", "PokerStars.ES"),
    ("pokerstars.pt", "PokerStars.PT"),
    ("pokerstars.eu", "PokerStars.EU"),
    ("pokerstars.de", "PokerStars.DE"),
    ("pokerstars.com", "PokerStars.COM"),
    ("pokerstarsfr", "PokerStars.FR"),
    ("pokerstarsit", "PokerStars.IT"),
    ("pokerstarses", "PokerStars.ES"),
    ("pokerstarspt", "PokerStars.PT"),
    ("pokerstarseu", "PokerStars.EU"),
    ("pokerstarsde", "PokerStars.DE"),
    ("pokerstarscom", "PokerStars.COM"),
]

# Hero name suffixes for skin detection
POKERSTARS_HERO_SUFFIXES = [
    (".fr", "_fr", "PokerStars.FR"),
    (".it", "_it", "PokerStars.IT"),
    (".es", "_es", "PokerStars.ES"),
    (".pt", "_pt", "PokerStars.PT"),
    (".eu", "_eu", "PokerStars.EU"),
    (".de", "_de", "PokerStars.DE"),
    (".com", "_com", "PokerStars.COM"),
]

# Regex patterns for parsing poker hand phases
PREFLOP_PATTERN = (
    r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>(.+(?P<FLOPET>\[\S\S\]))?"
    r".+(?=\*\*\* (FIRST\s)?FLOP \*\*\*)|.+)"
)
FLOP_PATTERN = (
    r"(\*\*\* FLOP \*\*\*(?P<FLOP> (\[\S\S\] )?\[(\S\S ?)?\S\S \S\S\]"
    r".+(?=\*\*\* (FIRST\s)?TURN \*\*\*)|.+))?"
)
TURN_PATTERN = (
    r"(\*\*\* TURN \*\*\* \[\S\S \S\S \S\S] (?P<TURN>\[\S\S\]"
    r".+(?=\*\*\* (FIRST\s)?RIVER \*\*\*)|.+))?"
)
RIVER_PATTERN = r"(\*\*\* RIVER \*\*\* \[\S\S \S\S \S\S \S\S] (?P<RIVER>\[\S\S\].+))?"
FIRST_FLOP_PATTERN = (
    r"(\*\*\* FIRST FLOP \*\*\*(?P<FLOP1> (\[\S\S\] )?\[(\S\S ?)?\S\S \S\S\]"
    r".+(?=\*\*\* FIRST TURN \*\*\*)|.+))?"
)
FIRST_TURN_PATTERN = (
    r"(\*\*\* FIRST TURN \*\*\* \[\S\S \S\S \S\S] (?P<TURN1>\[\S\S\]"
    r".+(?=\*\*\* FIRST RIVER \*\*\*)|.+))?"
)
FIRST_RIVER_PATTERN = (
    r"(\*\*\* FIRST RIVER \*\*\* \[\S\S \S\S \S\S \S\S] (?P<RIVER1>\[\S\S\]"
    r".+?(?=\*\*\* SECOND (FLOP|TURN|RIVER) \*\*\*)|.+))?"
)
SECOND_FLOP_PATTERN = (
    r"(\*\*\* SECOND FLOP \*\*\*(?P<FLOP2> (\[\S\S\] )?\[\S\S ?\S\S \S\S\]"
    r".+(?=\*\*\* SECOND TURN \*\*\*)|.+))?"
)
SECOND_TURN_PATTERN = (
    r"(\*\*\* SECOND TURN \*\*\* \[\S\S \S\S \S\S] (?P<TURN2>\[\S\S\]"
    r".+(?=\*\*\* SECOND RIVER \*\*\*)|.+))?"
)
SECOND_RIVER_PATTERN = r"(\*\*\* SECOND RIVER \*\*\* \[\S\S \S\S \S\S \S\S] (?P<RIVER2>\[\S\S\].+))?"

# Run-it-twice patterns for split pots
RIT_PREFLOP_PATTERN = r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>.+(?=\*\*\* FIRST\sFLOP \*\*\*)|.+)"
RIT_FIRST_FLOP_PATTERN = (
    r"(\*\*\* FIRST FLOP \*\*\* (?P<FLOP1>\[(\S\S ?)?\S\S \S\S\]"
    r".+(?=\*\*\* SECOND\sFLOP \*\*\*)|.+))?"
)
RIT_SECOND_FLOP_PATTERN = (
    r"(\*\*\* SECOND FLOP \*\*\* (?P<FLOP2>\[(\S\S ?)?\S\S \S\S\]"
    r".+(?=\*\*\* FIRST\sTURN \*\*\*)|.+))?"
)
RIT_FIRST_TURN_PATTERN = (
    r"(\*\*\* FIRST TURN \*\*\* \[\S\S \S\S \S\S] (?P<TURN1>\[\S\S\]"
    r".+(?=\*\*\* SECOND TURN \*\*\*)|.+))?"
)
RIT_SECOND_TURN_PATTERN = (
    r"(\*\*\* SECOND TURN \*\*\* \[\S\S \S\S \S\S] (?P<TURN2>\[\S\S\]"
    r".+(?=\*\*\* FIRST RIVER \*\*\*)|.+))?"
)
RIT_FIRST_RIVER_PATTERN = (
    r"(\*\*\* FIRST RIVER \*\*\* \[\S\S \S\S \S\S \S\S] (?P<RIVER1>\[\S\S\]"
    r".+?(?=\*\*\* SECOND RIVER \*\*\*)|.+))?"
)
RIT_SECOND_RIVER_PATTERN = r"(\*\*\* SECOND RIVER \*\*\* \[\S\S \S\S \S\S \S\S] (?P<RIVER2>\[\S\S\].+))?"


class PokerStars(HandHistoryConverter):
    """PokerStars hand history converter.

    Converts PokerStars hand history text files into FPDB database format.
    Supports multiple PokerStars skins and automatic skin detection based on
    file paths, content patterns, and hero names.

    Attributes:
        sitename: Name of the poker site
        filetype: Type of input files (text)
        codepage: Supported character encodings
        siteId: Numeric site identifier (overridden by skin detection)
        sym: Currency symbol mappings
        substitutions: Regex substitution patterns
        Lim_Blinds: Blind level mappings
    """
    # Class Variables

    sitename = "PokerStars"
    filetype = "text"
    codepage = ("utf8", "cp1252", "ISO-8859-1")
    site_id = 32  # Default to PokerStars.COM, will be overridden by detectPokerStarsSkin
    sym: ClassVar[dict[str, str]] = {
        "USD": r"\$",
        "CAD": r"\$",
        "T$": "",
        "EUR": "\xe2\x82\xac",
        "GBP": r"\£",
        "play": "",
        "INR": r"\₹",
        "CNY": r"\¥",
    }  # ADD Euro, Sterling, etc HERE
    substitutions: ClassVar[dict[str, str]] = {
        "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP|SC|INR|CNY",  # legal ISO currency codes
        "LS": r"\$|\xe2\x82\xac|\u20ac|\£|\u20b9|\¥|Rs\.\s|",  # legal currency symbols - Euro(cp1252, utf-8)
        "PLYR": r"\s?(?P<PNAME>.+?)",
        "CUR": r"(\$|\xe2\x82\xac|\u20ac||\£|\u20b9|\¥|Rs\.\s|)",
        "BRKTS": (
            r"(\(button\) |\(small blind\) |\(big blind\) |\(button blind\) |"
            r"\(button\) \(small blind\) |\(small blind\) \(button\) |"
            r"\(big blind\) \(button\) |\(small blind/button\) |"
            r"\(button\) \(big blind\) )?"
        ),
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
        "NO LIMIT": "nl",
        "Pot Limit": "pl",
        "POT LIMIT": "pl",
        "Fixed Limit": "fl",
        "Limit": "fl",
        "LIMIT": "fl",
        "Pot Limit Pre-Flop, No Limit Post-Flop": "pn",
    }
    games: ClassVar[dict[str, tuple[str, str]]] = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "HOLD'EM": ("hold", "holdem"),
        "6+ Hold'em": ("hold", "6_holdem"),
        "Omaha": ("hold", "omahahi"),
        "Fusion": ("hold", "fusion"),
        "OMAHA": ("hold", "omahahi"),
        "Omaha Hi/Lo": ("hold", "omahahilo"),
        "OMAHA HI/LO": ("hold", "omahahilo"),
        "5 Card Omaha": ("hold", "5_omahahi"),
        "Omaha 5 Cards": ("hold", "5_omahahi"),
        "5 Card Omaha Hi/Lo": ("hold", "5_omaha8"),
        "6 Card Omaha": ("hold", "6_omahahi"),
        "6 Card Omaha Hi/Lo": ("hold", "6_omaha8"),
        "Omaha 6 Cards": ("hold", "6_omahahi"),
        "Courchevel": ("hold", "cour_hi"),
        "Courchevel Hi/Lo": ("hold", "cour_hilo"),
        "Razz": ("stud", "razz"),
        "RAZZ": ("stud", "razz"),
        "7 Card Stud": ("stud", "studhi"),
        "7 CARD STUD": ("stud", "studhi"),
        "7 Card Stud Hi/Lo": ("stud", "studhilo"),
        "7 CARD STUD HI/LO": ("stud", "studhilo"),
        "Badugi": ("draw", "badugi"),
        "Triple Draw 2-7 Lowball": ("draw", "27_3draw"),
        "Single Draw 2-7 Lowball": ("draw", "27_1draw"),
        "5 Card Draw": ("draw", "fivedraw"),
    }
    mixes: ClassVar[dict[str, str]] = {
        "HORSE": "horse",
        "8-Game": "8game",
        "8-GAME": "8game",
        "HOSE": "hose",
        "Mixed PLH/PLO": "plh_plo",
        "Mixed NLH/PLO": "nlh_plo",
        "Mixed Omaha H/L": "plo_lo",
        "Mixed Hold'em": "mholdem",
        "Mixed Omaha": "momaha",
        "Triple Stud": "3stud",
    }  # Legal mixed games
    currencies: ClassVar[dict[str, str]] = {
        "€": "EUR",
        "$": "USD",
        "": "T$",
        "£": "GBP",
        "¥": "CNY",
        "₹": "INR",
        "Rs. ": "INR",
    }

    # Static regexes
    re_game_info = re.compile(
        """
          (?P<SITE>PokerStars|POKERSTARS|Hive\\sPoker|Full\\sTilt|PokerMaster|Run\\sIt\\sOnce\\sPoker|BetOnline|PokerBros|MPLPoker|SupremaPoker)(?P<TITLE>\\sGame|\\sHand|\\sHome\\sGame|\\sHome\\sGame\\sHand|Game|\\s(Zoom|Rush)\\sHand|\\sGAME)\\s\\#(?P<HID>[0-9]+):\\s+
          (\\{{.*\\}}\\s+)?((?P<TOUR>((Zoom|Rush)\\s)?(Tournament|TOURNAMENT))\\s\\#                # tournament info
          (?P<TOURNO>\\d+),\\s(Table\\s\\#(?P<HIVETABLE>\\d+),\\s)?
          # here's how I plan to use LS
          (?P<BUYIN>(?P<BIAMT>[{LS}\\d\\.]+)?\\+?(?P<BIRAKE>[{LS}\\d\\.]+)?\\+?(?P<BOUNTY>[{LS}\\d\\.]+)?\\s?(?P<TOUR_ISO>{LEGAL_ISO})?|Freeroll|)(\\s+)?(-\\s)?
          (\\s.+?,)?
          )?
          # close paren of tournament info
          (?P<MIXED>HORSE|8\\-Game|8\\-GAME|HOSE|Mixed\\sOmaha\\sH/L|Mixed\\sHold\'em|Mixed\\sPLH/PLO|Mixed\\sNLH/PLO|Mixed\\sOmaha|Triple\\sStud)?\\s?\\(?
          (?P<SPLIT>Split)?\\s?
          (?P<GAME>Hold\'em|HOLD\'EM|Hold\'em|6\\+\\sHold\'em|Razz|RAZZ|Fusion|7\\sCard\\sStud|7\\sCARD\\sSTUD|7\\sCard\\sStud\\sHi/Lo|7\\sCARD\\sSTUD\\sHI/LO|Omaha|OMAHA|Omaha\\sHi/Lo|OMAHA\\sHI/LO|Badugi|Triple\\sDraw\\s2\\-7\\sLowball|Single\\sDraw\\s2\\-7\\sLowball|5\\sCard\\sDraw|(5|6)\\sCard\\sOmaha(\\sHi/Lo)?|Omaha\\s(5|6)\\sCards|Courchevel(\\sHi/Lo)?)\\s
          (?P<LIMIT>No\\sLimit|NO\\sLIMIT|Fixed\\sLimit|Limit|LIMIT|Pot\\sLimit|POT\\sLIMIT|Pot\\sLimit\\sPre\\-Flop,\\sNo\\sLimit\\sPost\\-Flop)\\)?,?\\s
          (-\\s)?
          (?P<SHOOTOUT>Match.*,\\s)?
          ((Level|LEVEL)\\s(?P<LEVEL>[IVXLC\\d]+)\\s)?
          \\(?                            # open paren of the stakes
          (?P<CURRENCY>{LS}|)?
          (ante\\s\\d+,\\s)?
          ((?P<SB>[.0-9]+)/({LS})?(?P<BB>[.0-9]+)|Button\\sBlind\\s(?P<CURRENCY1>{LS}|)(?P<BUB>[.0-9]+)\\s\\-\\sAnte\\s({LS})?[.0-9]+\\s)
          (?P<CAP>\\s-\\s[{LS}]?(?P<CAPAMT>[.0-9]+)\\sCap\\s-\\s)?        # Optional Cap part
          \\s?(?P<ISO>{LEGAL_ISO})?
          \\)                        # close paren of the stakes
          (?P<BLAH2>\\s\\[(ADM|AAMS)\\sID:\\s[A-Z0-9]+\\])?         # AAMS/ADM ID: in .it HH's
          \\s-\\s
          (?P<DATETIME>.*$)
        """.format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_player_info = re.compile(
        r"""
          \s?Seat\s(?P<SEAT>[0-9]+):\s
          (?P<PNAME>.*)\s
          \(({LS})?(?P<CASH>[,.0-9]+)\sin\schips
          (,\s({LS})?(?P<BOUNTY>[,.0-9]+)\sbounty)?
          \)
          (?P<SITOUT>\sis\ssitting\sout)?""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    re_hand_info = re.compile(
        """
          \\s?Table\\s(ID\\s)?\'(?P<TABLE>.+?)\'(\\(\\d+\\))?\\s
          ((?P<MAX>\\d+)-[Mm]ax\\s)?
          (?P<PLAY>\\(Play\\sMoney\\)\\s)?
          (\\(Real\\sMoney\\)\\s)?
          (Seat\\s\\#(?P<BUTTON>\\d+)\\sis\\sthe\\sbutton)?""",
        re.MULTILINE | re.VERBOSE,
    )

    re_identify = re.compile(
        r"(PokerStars|POKERSTARS|Hive\sPoker|Full\sTilt|PokerMaster|Run\sIt\sOnce\sPoker|BetOnline|PokerBros|MPLPoker|SupremaPoker)(\sGame|\sHand|\sHome\sGame|\sHome\sGame\sHand|Game|\s(Zoom|Rush)\sHand|\sGAME)\s\#\d+:",
    )
    re_split_hands = re.compile("(?:\\s?\n){2,}")
    re_tail_split_hands = re.compile("(\n\n\n+)")
    re_button = re.compile(r"Seat #(?P<BUTTON>\d+) is the button", re.MULTILINE)
    re_board = re.compile(r"\[(?P<CARDS>.+)\]")
    re_board2 = re.compile(r"\[(?P<C1>\S\S)\] \[(\S\S)?(?P<C2>\S\S) (?P<C3>\S\S)\]")
    re_date_time1 = re.compile(
        r"""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""",
        re.MULTILINE,
    )
    re_date_time2 = re.compile(
        r"""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+)""",
        re.MULTILINE,
    )
    # revised re including timezone (not currently used)

    # These used to be compiled per player, but regression tests say
    # we don't have to, and it makes life faster.
    re_post_sb = re.compile(
        r"{PLYR}: posts small blind {CUR}(?P<SB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_post_bb = re.compile(
        r"{PLYR}: posts big blind {CUR}(?P<BB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_post_bub = re.compile(
        r"{PLYR}: posts button blind {CUR}(?P<BUB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_antes = re.compile(
        r"{PLYR}: posts the ante {CUR}(?P<ANTE>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_bring_in = re.compile(
        r"{PLYR}: brings[- ]in( low|) for {CUR}(?P<BRINGIN>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_post_both = re.compile(
        r"{PLYR}: posts small \& big blinds {CUR}(?P<SBBB>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_post_straddle = re.compile(
        r"{PLYR}: posts straddle {CUR}(?P<STRADDLE>[,.0-9]+)".format(**substitutions),
        re.MULTILINE,
    )
    try:
        re_action = re.compile(
            r"""{PLYR}:(?P<ATYPE>\sbets|\schecks|\sraises|\scalls|\sfolds|\sdiscards|\sstands\spat)(\s{CUR}(?P<BET>[,.\d]+))?(\sto\s{CUR}(?P<BETTO>[,.\d]+))?\s*(and\sis\sall.in)?(and\shas\sreached\sthe\s[{CUR}\d\.,]+\scap)?(\son|\scards?)?(\s\(disconnect\))?(\s\[(?P<CARDS>.+?)\])?\s*$""".format(
                **substitutions,
            ),
            re.MULTILINE | re.VERBOSE,
        )
    except Exception:
        log.exception("Error compiling re_action")

    re_showdown_action = re.compile(
        r"{}: (shows|mucks|mucked|showed) \[(?P<CARDS>.*)\]".format(substitutions["PLYR"]),
        re.MULTILINE,
    )
    re_sits_out = re.compile("{} sits out".format(substitutions["PLYR"]), re.MULTILINE)
    re_collect_pot = re.compile(
        r"Seat (?P<SEAT>[0-9]+): {PLYR} {BRKTS}"
        r"(collected|showed \[.*\] and (won|collected)) "
        r"\(?{CUR}(?P<POT>[,.\d]+)\)?(, mucked| with.*|)".format(
            **substitutions,
        ),
        re.MULTILINE,
    )
    # Vinsand88 cashed out the hand for $2.19 | Cash Out Fee $0.02
    re_collect_pot2 = re.compile(
        r"{PLYR} collected {CUR}(?P<POT>[,.\d]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_collect_pot3 = re.compile(
        r"{PLYR} cashed out the hand for {CUR}(?P<POT>[,.\d]+) \| Cash Out Fee {CUR}(?P<FEE>[,.\d]+)".format(**substitutions),
        re.MULTILINE,
    )
    re_cashed_out = re.compile(r"cashed\sout\sthe\shand")
    re_winning_rank_one = re.compile(
        r"{PLYR} wins the tournament and receives {CUR}(?P<AMT>[,\.0-9]+) - congratulations!$".format(**substitutions),
        re.MULTILINE,
    )
    re_winning_rank_other = re.compile(
        r"{PLYR} finished the tournament in (?P<RANK>[0-9]+)(st|nd|rd|th) place "
        r"and received {CUR}(?P<AMT>[,.0-9]+)\.$".format(
            **substitutions,
        ),
        re.MULTILINE,
    )
    re_rank_other = re.compile(
        r"{PLYR} finished the tournament in (?P<RANK>[0-9]+)(st|nd|rd|th) place$".format(**substitutions),
        re.MULTILINE,
    )
    re_cancelled = re.compile(r"Hand\scancelled", re.MULTILINE)
    re_uncalled = re.compile(
        r"Uncalled bet \({CUR}(?P<BET>[,.\d]+)\) returned to {PLYR}$".format(**substitutions),
        re.MULTILINE,
    )
    re_empty_card = re.compile(r"\[\]", re.MULTILINE)
    # APTEM-89 wins the $0.27 bounty for eliminating Hero
    # ChazDazzle wins the 22000 bounty for eliminating berkovich609
    # JKuzja, vecenta split the $50 bounty for eliminating ODYSSES
    re_bounty = re.compile(
        r"{PLYR} (?P<SPLIT>split|wins) the {CUR}(?P<AMT>[,\.0-9]+) bounty for eliminating (?P<ELIMINATED>.+?)$".format(
            **substitutions,
        ),
        re.MULTILINE,
    )
    # Amsterdam71 wins $19.90 for eliminating MuKoJla and their own bounty increases by $19.89 to $155.32
    # Amsterdam71 wins $4.60 for splitting the elimination of Frimble11 and their own bounty
    # increases by $4.59 to $41.32
    # Amsterdam71 wins the tournament and receives $230.36 - congratulations!
    re_progressive = re.compile(
        r"""
                        {PLYR}\swins\s{CUR}(?P<AMT>[,\.0-9]+)\s
                        for\s(splitting\sthe\selimination\sof|eliminating)\s(?P<ELIMINATED>.+?)\s
                        and\stheir\sown\sbounty\sincreases\sby\s{CUR}(?P<INCREASE>[\.0-9]+)\sto\s{CUR}(?P<ENDAMT>[\.0-9]+)$""".format(
            **substitutions,
        ),
        re.MULTILINE | re.VERBOSE,
    )
    re_rake = re.compile(
        r"""
                        Total\spot\s{CUR}(?P<POT>[,\.0-9]+)(.+?)?\s\|\sRake\s{CUR}(?P<RAKE>[,\.0-9]+)""".format(
            **substitutions,
        ),
        re.MULTILINE | re.VERBOSE,
    )

    re_stp = re.compile(
        r"""
                        STP\sadded:\s{CUR}(?P<AMOUNT>[,\.0-9]+)""".format(**substitutions),
        re.MULTILINE | re.VERBOSE,
    )

    # Regex patterns to detect the different PokerStars skins
    re_pokerstars_fr = re.compile(r"PokerStars\.fr", re.IGNORECASE)
    re_pokerstars_it = re.compile(r"PokerStars\.it", re.IGNORECASE)
    re_pokerstars_es = re.compile(r"PokerStars\.es", re.IGNORECASE)
    re_pokerstars_pt = re.compile(r"PokerStars\.pt", re.IGNORECASE)
    re_pokerstars_eu = re.compile(r"PokerStars\.eu", re.IGNORECASE)
    re_pokerstars_de = re.compile(r"PokerStars\.de", re.IGNORECASE)
    re_pokerstars_com = re.compile(r"PokerStars\.com", re.IGNORECASE)

    def loadHeroMappings(self) -> dict[str, str]:
        """Loads hero-to-skin mappings from configuration file.

        Reads the 'pokerstars_skin_mapping.conf' file and returns a dictionary mapping hero names to PokerStars skin names.

        Returns:
            dict[str, str]: Mapping of hero names (lowercase) to skin names.
        """
        import configparser

        mappings = {}
        config_file = Path(__file__).parent / "pokerstars_skin_mapping.conf"

        if config_file.exists():
            config = configparser.ConfigParser()
            try:
                config.read(config_file)
                if "hero_mapping" in config:
                    for hero, skin in config["hero_mapping"].items():
                        mappings[hero.lower()] = skin
            except (FileNotFoundError, KeyError, ValueError) as e:
                log.warning("Error loading mapping file: %s", e)

        return mappings

    def _detectSkinByHero(self, hand_text: str) -> tuple[str, int] | None:
        """Detects PokerStars skin using hero name mapping.

        Checks the hand text for the hero name and returns the corresponding skin and site ID if a mapping exists.

        Args:
            hand_text (str): The hand history text to search for the hero name.

        Returns:
            tuple[str, int] | None: The skin name and site ID if found, otherwise None.
        """
        hero_match = re.search(r"Dealt to ([^\[]+)", hand_text[:500])
        if not hero_match:
            return None

        hero_name = hero_match[1].strip()

        # Load mappings if not already done
        if not hasattr(self, "_hero_mappings"):
            self._hero_mappings = self.loadHeroMappings()

        # Check whether the hero has a mapping
        hero_lower = hero_name.lower()
        if hero_lower in self._hero_mappings:
            skin = self._hero_mappings[hero_lower]
            if skin in POKERSTARS_SKIN_IDS:
                return skin, POKERSTARS_SKIN_IDS[skin]
        return None

    def _detectSkinByPath(self, file_path: str) -> tuple[str, int] | None:
        """Detects PokerStars skin using the file path.

        Searches the file path for known patterns to identify the PokerStars skin and its site ID.

        Args:
            file_path (str): The file path to check for skin patterns.

        Returns:
            tuple[str, int] | None: The skin name and site ID if found, otherwise None.
        """
        # Normalise the path for comparison
        path_lower = file_path.lower().replace("\\", "/")

        # Search for typical path patterns for each skin
        try:
            return next(
                (skin_name, POKERSTARS_SKIN_IDS[skin_name])
                for pattern, skin_name in POKERSTARS_PATH_PATTERNS
                if pattern in path_lower
            )
        except StopIteration:
            return None

    def detectPokerStarsSkin(self, hand_text: str, file_path: str | None = None) -> tuple[str, int]:
        """Detects the PokerStars skin and site ID from hand text and file path.

        Determines the PokerStars skin by checking hero mappings, file path patterns, and hand text content.

        Args:
            hand_text (str): The hand history text to analyze.
            file_path (str | None): The file path to check for skin patterns.

        Returns:
            tuple[str, int]: The detected skin name and site ID.
        """
        # First, check whether the hero has a mapping configured
        if hero_result := self._detectSkinByHero(hand_text):
            return hero_result

        # Then try to detect the path
        if file_path and (path_result := self._detectSkinByPath(file_path)):
            return path_result

        # Finally, analyze content
        return self._detectSkinByContent(hand_text)

    def _detectSkinByContent(self, hand_text: str) -> tuple[str, int]:
        """Detects PokerStars skin using hand text content.

        Analyzes the hand text for country-specific IDs, hero name clues, regex patterns, and currency to determine the PokerStars skin and site ID.

        Args:
            hand_text (str): The hand history text to analyze.

        Returns:
            tuple[str, int]: The detected skin name and site ID.
        """
        search_text = hand_text[:2000]

        # Verification of AAMS/ADM ID for Italy
        if "AAMS ID:" in search_text or "ADM ID:" in search_text:
            return "PokerStars.IT", SITE_POKERSTARS_IT

        # Try to detect via hero name if it contains clues
        if hero_match := re.search(r"Dealt to ([^\[]+)", hand_text[:500]):
            hero_name = hero_match[1].strip()
            hero_lower = hero_name.lower()
            # CSome players include the skin in their name.
            for suffix1, suffix2, skin_name in POKERSTARS_HERO_SUFFIXES:
                if suffix1 in hero_lower or suffix2 in hero_lower:
                    return skin_name, POKERSTARS_SKIN_IDS[skin_name]

        # Search for specific patterns in content using regex
        regex_tests = [
            (self.re_pokerstars_fr, "PokerStars.FR"),
            (self.re_pokerstars_it, "PokerStars.IT"),
            (self.re_pokerstars_es, "PokerStars.ES"),
            (self.re_pokerstars_pt, "PokerStars.PT"),
            (self.re_pokerstars_eu, "PokerStars.EU"),
            (self.re_pokerstars_de, "PokerStars.DE"),
            (self.re_pokerstars_com, "PokerStars.COM"),
        ]

        if match := next(((regex, skin_name) for regex, skin_name in regex_tests if regex.search(search_text)), None):
            regex, skin_name = match
            return skin_name, POKERSTARS_SKIN_IDS[skin_name]

        # As a last resort, use the currency
        if "€" in search_text or "EUR" in search_text:
            return "PokerStars.EU", SITE_POKERSTARS_EU
        # The default setting is PokerStars.COM
        return "PokerStars.COM", SITE_POKERSTARS_COM

    def readOther(self, hand: "Hand") -> None:
        """Read other information from hand text."""

    def allHandsAsList(self) -> list[str]:
        """Returns a cleaned list of all hand texts.

        Processes the raw hand list to remove empty hands, split multiple hands, and clean up archive formats.

        Returns:
            list[str]: A list of cleaned hand history texts.
        """
        # Call parent implementation first
        handlist = super().allHandsAsList()

        # Log what we got
        log.info("PokerStars allHandsAsList: got %d hands", len(handlist))

        # Clean up archive formats and handle multiple hands
        cleaned_handlist = []
        for i, hand_text in enumerate(handlist):
            log.debug("Processing hand %d/%d", i+1, len(handlist))
            
            # Skip empty hands
            if not hand_text.strip():
                log.debug("Skipping empty hand %d", i+1)
                continue
            
            # Check for multiple hands in a single text block (common with partial files)
            summary_count = hand_text.count("*** SUMMARY ***")
            if summary_count > 1:
                log.info(f"Hand {i+1} contains {summary_count} summaries, attempting to split...")
                # Try to split multiple hands more intelligently
                sub_hands = self._split_multiple_hands(hand_text)
                cleaned_handlist.extend(sub_hands)
                continue
                
            # Check if this hand has the problematic archive format with stars
            if "*" * 10 in hand_text:
                log.info("Found archive format in hand %d, cleaning...", i+1)
                # Remove the star line and clean up leading spaces
                lines = hand_text.split("\n")
                cleaned_lines = []
                for original_line in lines:
                    # Skip star delimiter lines
                    if original_line.strip().startswith("*" * 10):
                        continue
                    # Remove leading space that causes " Player1" issue
                    cleaned_line = original_line
                    if cleaned_line.startswith(" ") and not cleaned_line.startswith("  "):
                        cleaned_line = cleaned_line[1:]
                    cleaned_lines.append(cleaned_line)
                if cleaned_text := "\n".join(cleaned_lines).strip():
                    cleaned_handlist.append(cleaned_text)
            else:
                cleaned_handlist.append(hand_text)

        log.info("PokerStars allHandsAsList: returning %d cleaned hands", len(cleaned_handlist))
        return cleaned_handlist

    def _split_multiple_hands(self, text: str) -> list[str]:
        """Splits a text block containing multiple PokerStars hands into individual hand texts.

        Finds hand boundaries using PokerStars hand headers and returns a list of complete hand texts containing a summary.

        Args:
            text (str): The raw hand history text block to split.

        Returns:
            list[str]: A list of individual hand history texts with summaries.
        """
        hands = []
        
        # Find all hand starts
        hand_pattern = r'PokerStars (Game|Hand) #\d+'
        hand_starts = list(re.finditer(hand_pattern, text))
        
        if len(hand_starts) <= 1:
            # Only one or no hand headers found, return as is
            return [text.strip()] if text.strip() else []
        
        # Split based on hand boundaries
        for i, match in enumerate(hand_starts):
            start_pos = match.start()
            if i + 1 < len(hand_starts):
                # Not the last hand
                end_pos = hand_starts[i + 1].start()
                hand_text = text[start_pos:end_pos].strip()
            else:
                # Last hand
                hand_text = text[start_pos:].strip()
            
            if hand_text and "*** SUMMARY ***" in hand_text:
                hands.append(hand_text)
                log.debug(f"Extracted hand: {hand_text[:50]}...")
            elif hand_text:
                # Hand without summary - might be incomplete
                log.warning(f"Found hand without summary, skipping: {hand_text[:50]}...")
        
        log.info(f"Split multiple hands: {len(hands)} valid hands extracted")
        return hands

    def compilePlayerRegexs(self, hand: "Hand") -> None:
        """Compiles player-specific regular expressions for parsing hand text.

        Generates and stores regex patterns for hero cards and shown cards based on the current set of players in the hand.

        Args:
            hand ("Hand"): The hand object containing player information.

        Returns:
            None
        """
        players = {player[1] for player in hand.players}
        if not players <= self.compiledPlayers:  # x <= y means 'x is subset of y'
            self.compiledPlayers = players
            player_re = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"
            subst = {
                "PLYR": player_re,
                "BRKTS": (
                    r"(\(button\) |\(small blind\) |\(big blind\) |"
                    r"\(button\) \(small blind\) |\(button\) \(big blind\) )?"
                ),
                "CUR": "(\\$|\xe2\x82\xac|\u20ac||\\£|)",
            }
            if self.siteId == SITE_MERGE:
                self.re_hero_cards = re.compile(
                    r"Dealt\sto\s(?P<PNAME>(?![A-Z][a-z]+\s[A-Z]).+?)"
                    r"(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(),
                    re.MULTILINE,
                )
                self.re_shown_cards = re.compile(
                    r"Seat (?P<SEAT>[0-9]+): {PLYR} {BRKTS}(?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]"
                    r"( and (lost|(won|collected) {CUR}(?P<POT>[,\.\d]+) with (?P<STRING>.+?))"
                    r"(,\sand\s(lost|won\s{CUR}[\.\d]+\swith\s(?P<STRING2>.*)))?)?$".format(
                        **subst,
                    ),
                    re.MULTILINE,
                )
            else:
                self.re_hero_cards = re.compile(
                    r"Dealt to {PLYR}(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(**subst),
                    re.MULTILINE,
                )
                self.re_shown_cards = re.compile(
                    r"Seat (?P<SEAT>[0-9]+): {PLYR} {BRKTS}(?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]"
                    r"( and (lost|(won|collected) \({CUR}(?P<POT>[,\.\d]+)\)) with (?P<STRING>.+?)"
                    r"(,\sand\s(won\s\({CUR}[\.\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?$".format(
                        **subst,
                    ),
                    re.MULTILINE,
                )

    def readSupportedGames(self) -> list[list[str]]:
        """Returns a list of supported game types for PokerStars.

        Provides all combinations of game format, base game, and limit type that are supported for parsing.

        Returns:
            list[list[str]]: A list of supported game type descriptors.
        """
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

    def _parseBasicGameInfo(self, mg: dict) -> dict[str, str]:
        """Parses basic game information from regex match groups.

        Extracts limit type, base game, category, blinds, currency, and mix type from the provided match group dictionary.

        Args:
            mg (dict): Dictionary of regex match groups containing game info.

        Returns:
            dict[str, str]: Dictionary of parsed basic game information.
        """
        info = {}

        if "LIMIT" in mg:
            info["limitType"] = self.limits[mg["LIMIT"]]
        if "GAME" in mg:
            (info["base"], info["category"]) = self.games[mg["GAME"]]
        if "SB" in mg and mg["SB"] is not None:
            info["sb"] = mg["SB"]
        if "BB" in mg and mg["BB"] is not None:
            info["bb"] = mg["BB"]
        if "BUB" in mg and mg["BUB"] is not None:
            info["sb"] = "0"
            info["bb"] = mg["BUB"]
        if "CURRENCY1" in mg and mg["CURRENCY1"] is not None:
            info["currency"] = self.currencies[mg["CURRENCY1"]]
        elif "CURRENCY" in mg:
            info["currency"] = self.currencies[mg["CURRENCY"]]
        if "MIXED" in mg and mg["MIXED"] is not None:
            info["mix"] = self.mixes[mg["MIXED"]]

        return info

    def _parseGameFlags(self, mg: dict) -> dict[str, bool]:
        """Parses game flags from match group dictionary.

        Determines game attributes such as fast format, home game, split game, and buyin type from the provided match group.

        Args:
            mg (dict): Dictionary of regex match groups containing game info.

        Returns:
            dict[str, bool]: Dictionary of parsed game flags.
        """
        return {
            "fast": "Zoom" in mg["TITLE"] or "Rush" in mg["TITLE"],
            "homeGame": "Home" in mg["TITLE"],
            "split": "SPLIT" in mg and mg["SPLIT"] == "Split",
            "buyinType": "cap" if "CAP" in mg and mg["CAP"] is not None else "regular"
        }

    def _detectSiteType(self, mg: dict, hand_text: str, info: dict) -> None:
        """Detects the poker site type and updates site information.

        Sets the sitename and site_id based on the SITE value in the match group, and updates game category for specific sites.

        Args:
            mg (dict): Dictionary of regex match groups containing site info.
            hand_text (str): The hand history text to analyze.
            info (dict): Dictionary to update with site-specific game info.

        Returns:
            None
        """
        if mg["SITE"] == "PokerMaster":
            self.sitename = "PokerMaster"
            self.site_id = 25
            m1 = self.re_hand_info.search(hand_text, re.DOTALL)
            if m1 and "_5Cards_" in m1.group("TABLE"):
                info["category"] = "5_omahahi"
        elif mg["SITE"] == "Run It Once Poker":
            self.sitename = "Run It Once Poker"
            self.site_id = 26
        elif mg["SITE"] == "BetOnline":
            self.sitename = "BetOnline"
            self.site_id = 19
        elif mg["SITE"] == "PokerBros":
            self.sitename = "PokerBros"
            self.site_id = 29
        elif mg["SITE"] in ("PokerStars", "POKERSTARS"):
            # Detection of specific PokerStars skin
            self.sitename, self.site_id = self.detectPokerStarsSkin(
                hand_text,
                self.in_path if hasattr(self, "in_path") else None,
            )

    def determineGameType(self, hand_text: str) -> dict[str, str]:
        """Determines the game type and related attributes from hand text.

        Parses the hand text to extract game type, site, format, currency, and blind information for the current hand.

        Args:
            hand_text (str): The hand history text to analyze.

        Returns:
            dict[str, str]: Dictionary containing parsed game type and related attributes.
        """
        m = self.re_game_info.search(hand_text)
        if not m:
            tmp = hand_text[:200]
            log.error("determine Game Type failed: %r", tmp)
            raise FpdbParseError

        mg = m.groupdict()
        info = self._parseBasicGameInfo(mg)
        info.update(self._parseGameFlags(mg))

        # Site detection
        if "SITE" in mg:
            self._detectSiteType(mg, hand_text, info)

        # Tournament vs Ring game
        self._determineGameFormat(mg, info)

        # Currency and blind adjustments
        self._adjustCurrencyAndBlinds(mg, info, hand_text)

        return info

    def _determineGameFormat(self, mg: dict, info: dict) -> None:
        """Determines the game format as ring or tournament.

        Sets the game type in the info dictionary based on match group values, and marks fast format for Zoom tournaments.

        Args:
            mg (dict): Dictionary of regex match groups containing game info.
            info (dict): Dictionary to update with game format information.

        Returns:
            None
        """
        if "TOURNO" in mg and mg["TOURNO"] is None:
            info["type"] = "ring"
        else:
            info["type"] = "tour"
            if "TOUR" in mg and "ZOOM" in mg["TOUR"]:
                info["fast"] = True

    def _adjustCurrencyAndBlinds(self, mg: dict, info: dict, hand_text: str) -> None:
        """Adjusts currency and blind values based on game information.

        Updates the currency and small/big blind values in the info dictionary according to game type, limit type, and match group data.

        Args:
            mg (dict): Dictionary of regex match groups containing game info.
            info (dict): Dictionary to update with currency and blind information.
            hand_text (str): The hand history text for error reporting.

        Returns:
            None
        """
        if info.get("currency") in ("T$", None) and info["type"] == "ring":
            info["currency"] = "play"

        if info["limitType"] == "fl" and info["bb"] is not None:
            if info["type"] == "ring":
                try:
                    info["sb"] = self.lim_blinds[mg["BB"]][0]
                    info["bb"] = self.lim_blinds[mg["BB"]][1]
                except KeyError:
                    tmp = hand_text[:200]
                    log.exception("Lim_Blinds has no lookup for %r - %r", mg["BB"], tmp)
                    raise FpdbParseError from None
            else:
                sb_decimal = Decimal(mg["SB"]) / 2
                bb_decimal = Decimal(mg["SB"])
                info["sb"] = str(sb_decimal.quantize(Decimal("0.01")))
                info["bb"] = str(bb_decimal.quantize(Decimal("0.01")))

    def _processDateTime(self, datetime_str: str, hand: "Hand") -> None:
        """Processes and sets the hand start time from a date-time string.

        Parses the date-time string from the hand text and sets the hand's start time, converting to UTC if necessary.

        Args:
            datetime_str (str): The date-time string extracted from hand text.
            hand ("Hand"): The hand object to update with the parsed start time.

        Returns:
            None
        """
        # 2008/11/12 10:00:48 CET [2008/11/12 4:00:48 ET]
        # (both dates are parsed so ET date overrides the other)
        # 2008/08/17 - 01:14:43 (ET)
        # 2008/09/07 06:23:14 ET
        datetimestr = "2000/01/01 00:00:00"  # default used if time not found

        if self.siteId == SITE_MERGE:
            m2 = self.re_date_time2.finditer(datetime_str)
            for a in m2:
                datetimestr = f"{a.group('Y')}/{a.group('M')}/{a.group('D')} {a.group('H')}:{a.group('MIN')}:00"
            hand.startTime = datetime.datetime.strptime(  # noqa: DTZ007
                datetimestr,
                "%Y/%m/%d %H:%M:%S",
            )  # timezone handled by changeTimezone below
        else:
            m1 = self.re_date_time1.finditer(datetime_str)
            for a in m1:
                datetimestr = f"{a.group('Y')}/{a.group('M')}/{a.group('D')} {a.group('H')}:{a.group('MIN')}:{a.group('S')}"
            hand.startTime = datetime.datetime.strptime(  # noqa: DTZ007
                datetimestr,
                "%Y/%m/%d %H:%M:%S",
            )  # timezone handled by changeTimezone below
            hand.startTime = HandHistoryConverter.changeTimezone(
                hand.startTime,
                "ET",
                "UTC",
            )

    def _setFreeBuyin(self, hand: "Hand", currency: str) -> None:
        """Sets buyin and fee to zero for freeroll tournaments.

        Updates the hand object to reflect a free buyin and fee, and sets the buyin currency.

        Args:
            hand ("Hand"): The hand object to update.
            currency (str): The currency to set for the buyin.

        Returns:
            None
        """
        hand.buyin = 0
        hand.fee = 0
        hand.buyinCurrency = currency

    def _processBuyinInfo(self, info: dict, hand: "Hand") -> None:
        """Processes buyin information and updates the hand object.

        Determines buyin type, currency, bounty, and fee details from the info dictionary and sets relevant attributes on the hand object.

        Args:
            info (dict): Dictionary containing buyin and tournament information.
            hand ("Hand"): The hand object to update with buyin details.

        Returns:
            None
        """
        key = "BUYIN"
        if info[key].strip() == "Freeroll":
            self._setFreeBuyin(hand, "FREE")
        elif info[key].strip() == "":
            self._setFreeBuyin(hand, "NA")
        else:
            # Detect currency
            self._detectBuyinCurrency(info[key], hand)

            # Remove currency symbols from amount
            info["BIAMT"] = re.sub(r"^[$€£FPPSC₹]+|[$€£FPPSC₹]+$", "", info["BIAMT"])

            # Process bounty and fees
            self._processBountyAndFees(info, hand)

        # Process game flags
        hand.isFast = "Zoom" in info["TITLE"] or "Rush" in info["TITLE"]
        hand.isHomeGame = "Home" in info["TITLE"]

    def _detectBuyinCurrency(self, buyin_str: str, hand: "Hand") -> None:
        """Detects the buyin currency from the buyin string and updates the hand object.

        Analyzes the buyin string for currency symbols or keywords and sets the buyinCurrency attribute on the hand object.

        Args:
            buyin_str (str): The buyin string to analyze for currency.
            hand ("Hand"): The hand object to update with detected currency.

        Returns:
            None

        Raises:
            FpdbParseError: If the currency cannot be detected from the buyin string.
        """
        if "$" in buyin_str:
            hand.buyinCurrency = "USD"
        elif "£" in buyin_str:
            hand.buyinCurrency = "GBP"
        elif "€" in buyin_str:
            hand.buyinCurrency = "EUR"
        elif "₹" in buyin_str or "Rs. " in buyin_str:
            hand.buyinCurrency = "INR"
        elif "¥" in buyin_str:
            hand.buyinCurrency = "CNY"
        elif "FPP" in buyin_str or "SC" in buyin_str:
            hand.buyinCurrency = "PSFP"
        elif re.match("[0-9+]*$", buyin_str.strip()):
            hand.buyinCurrency = "play"
        else:
            log.error("Failed to detect currency. Hand ID: %s: %r", hand.handid, buyin_str)
            raise FpdbParseError

    def _swapBountyAndRake(self, info: dict) -> None:
        """Swaps the values of bounty and rake in the info dictionary.

        Exchanges the values of the 'BOUNTY' and 'BIRAKE' keys in the provided info dictionary.

        Args:
            info (dict): Dictionary containing bounty and rake information.

        Returns:
            None
        """
        info["BOUNTY"], info["BIRAKE"] = info["BIRAKE"], info["BOUNTY"]

    def _processBountyAndFees(self, info: dict, hand: "Hand") -> None:
        """Processes bounty and fee information for a hand.

        Calculates and sets the bounty, buyin, and fee values on the hand object based on the provided info dictionary.

        Args:
            info (dict): Dictionary containing bounty, rake, and buyin information.
            hand ("Hand"): The hand object to update with bounty and fee details.

        Returns:
            None
        """
        if hand.buyinCurrency != "PSFP":
            if info["BOUNTY"] is not None:
                self._swapBountyAndRake(info)
                info["BOUNTY"] = info["BOUNTY"].strip("$€£₹")
                hand.koBounty = int(100 * float(info["BOUNTY"]))
                hand.isKO = True
            else:
                hand.isKO = False

            info["BIRAKE"] = info["BIRAKE"].strip("$€£₹")
            hand.buyin = int(100 * float(info["BIAMT"])) + hand.koBounty
            hand.fee = int(100 * float(info["BIRAKE"]))
        else:
            hand.buyin = int(100 * float(info["BIAMT"]))
            hand.fee = 0

    def _processHandInfo(self, info: dict, hand: "Hand") -> None:
        """Processes extracted hand information and updates the hand object.

        Iterates through the info dictionary and delegates processing of each key to the appropriate handler.

        Args:
            info (dict): Dictionary containing extracted hand information.
            hand ("Hand"): The hand object to update with processed information.

        Returns:
            None
        """
        for key in info:
            self._processHandInfoKey(key, info, hand)

    def _processHandInfoKey(self, key: str, info: dict, hand: "Hand") -> None:
        """Processes a single key from the hand info dictionary and updates the hand object.

        Delegates processing of the key to the appropriate handler based on its type (basic, tournament, or table field).

        Args:
            key (str): The key from the hand info dictionary to process.
            info (dict): Dictionary containing extracted hand information.
            hand ("Hand"): The hand object to update with processed information.

        Returns:
            None
        """
        if key in {"DATETIME", "HID", "TOURNO"}:
            self._processBasicHandFields(key, info, hand)
        elif key in {"BUYIN", "LEVEL", "SHOOTOUT"}:
            self._processTournamentFields(key, info, hand)
        elif key in {"TABLE", "BUTTON", "MAX"}:
            self._processTableFields(key, info, hand)

    def _processBasicHandFields(self, key: str, info: dict, hand: "Hand") -> None:
        """Processes basic hand fields and updates the hand object.

        Handles the DATETIME, HID, and TOURNO keys by setting the corresponding attributes on the hand object.

        Args:
            key (str): The key from the hand info dictionary to process.
            info (dict): Dictionary containing extracted hand information.
            hand ("Hand"): The hand object to update with processed information.

        Returns:
            None
        """
        if key == "DATETIME":
            self._processDateTime(info[key], hand)
        elif key == "HID":
            hand.handid = info[key]
        elif key == "TOURNO" and info[key] is not None:
            hand.tourNo = info[key][-18:]

    def _processTournamentFields(self, key: str, info: dict, hand: "Hand") -> None:
        """Processes tournament-specific fields and updates the hand object.

        Handles the BUYIN, LEVEL, and SHOOTOUT keys by setting the corresponding tournament attributes on the hand object.

        Args:
            key (str): The key from the hand info dictionary to process.
            info (dict): Dictionary containing extracted hand information.
            hand ("Hand"): The hand object to update with processed tournament information.

        Returns:
            None
        """
        if key == "BUYIN" and hand.tourNo is not None:
            self._processBuyinInfo(info, hand)
        elif key == "LEVEL":
            hand.level = info[key]
        elif key == "SHOOTOUT" and info[key] is not None:
            hand.isShootout = True

    def _processTableFields(self, key: str, info: dict, hand: "Hand") -> None:
        """Processes table-related fields and updates the hand object.

        Handles the TABLE, BUTTON, and MAX keys by setting the corresponding table attributes on the hand object.

        Args:
            key (str): The key from the hand info dictionary to process.
            info (dict): Dictionary containing extracted hand information.
            hand ("Hand"): The hand object to update with processed table information.

        Returns:
            None
        """
        if key == "TABLE":
            self._processTableInfo(info, hand)
        elif key == "BUTTON":
            hand.buttonpos = info[key]
        elif key == "MAX" and info[key] is not None:
            hand.maxseats = int(info[key])

    def _processTableInfo(self, info: dict, hand: "Hand") -> None:
        """Processes table information and updates the hand object.

        Sets the table name on the hand object based on tournament and table info fields.

        Args:
            info (dict): Dictionary containing extracted hand information.
            hand ("Hand"): The hand object to update with table information.

        Returns:
            None
        """
        tablesplit = re.split(" ", info["TABLE"])
        if info["TOURNO"] is not None and info["HIVETABLE"] is not None:
            hand.tablename = info["HIVETABLE"]
        elif hand.tourNo is not None and len(tablesplit) > 1:
            hand.tablename = tablesplit[1]
        else:
            hand.tablename = info["TABLE"]

    def readHandInfo(self, hand: "Hand") -> None:
        """Reads and processes hand information from the hand text.

        Extracts summary, game, and table information from the hand text, checks for partial or malformed hands, and updates the hand object with parsed details.

        Args:
            hand ("Hand"): The hand object to update with extracted information.

        Returns:
            None

        Raises:
            FpdbHandPartial: If the hand is incomplete, contains multiple summaries, or is cancelled.
            FpdbParseError: If hand information cannot be parsed from the hand text.
        """
        # First check if partial or malformed
        summary_count = hand.handText.count("*** SUMMARY ***")
        
        if summary_count == 0:
            msg = f"Hand '{hand.handid}' has no SUMMARY section - likely incomplete"
            raise FpdbHandPartial(msg)
        elif summary_count > 1:
            # Multiple summaries suggest multiple hands in one string
            # Try to extract just the first complete hand
            if summaries := list(re.finditer(r'\*\*\* SUMMARY \*\*\*', hand.handText)):
                # Find the end of the first hand (after its summary section)
                first_summary_end = summaries[0].end()
                # Look for the next hand start or end of string
                remaining_text = hand.handText[first_summary_end:]
                if next_hand_match := re.search(r'\n\n+PokerStars (Game|Hand) #', remaining_text):
                    # Truncate to just the first hand
                    truncate_pos = first_summary_end + next_hand_match.start()
                    original_text = hand.handText
                    hand.handText = original_text[:truncate_pos].rstrip()
                    log.info(f"Hand '{hand.handid}' contained multiple hands, extracted first hand only")
                else:
                    # No clear next hand boundary, treat as partial
                    msg = f"Hand '{hand.handid}' contains {summary_count} SUMMARY sections - appears to contain multiple incomplete hands"
                    raise FpdbHandPartial(msg)
            else:
                msg = f"Hand '{hand.handid}' is not cleanly split into pre and post Summary"
                raise FpdbHandPartial(msg)

        info = {}
        m = self.re_hand_info.search(hand.handText, re.DOTALL)
        m2 = self.re_game_info.search(hand.handText)
        if m is None or m2 is None:
            tmp = hand.handText[:200]
            log.error("read Hand Info failed: %r", tmp)
            raise FpdbParseError

        info |= m.groupdict() | m2.groupdict()

        # Process the extracted information
        self._processHandInfo(info, hand)

        if "Zoom" in self.in_path or "Rush" in self.in_path:
            (hand.gametype["fast"], hand.isFast) = (True, True)

        if self.re_cancelled.search(hand.handText):
            msg = f"Hand '{hand.handid}' was cancelled."
            raise FpdbHandPartial(msg)

        # Parse rake and total pot from hand text if available
        self._parseRakeAndPot(hand)

    def readButton(self, hand: "Hand") -> None:
        """Reads the button position from the hand text and updates the hand object.

        Searches for the button position in the hand text and sets it on the hand object, logging if not found.

        Args:
            hand ("Hand"): The hand object to update with button position.

        Returns:
            None
        """
        if m := self.re_button.search(hand.handText):
            hand.buttonpos = int(m.group("BUTTON"))
        else:
            log.info("readButton: not found")

    def readPlayerStacks(self, hand: "Hand") -> None:
        """Reads player stack information from the hand text and updates the hand object.

        Extracts seat, player name, cash, sitout status, and bounty for each player before the summary section.

        Args:
            hand ("Hand"): The hand object to update with player stack information.

        Returns:
            None
        """
        pre, post = hand.handText.split("*** SUMMARY ***")
        m = self.re_player_info.finditer(pre)
        for a in m:
            hand.addPlayer(
                int(a.group("SEAT")),
                a.group("PNAME"),
                self.clearMoneyString(a.group("CASH")),
                None,
                a.group("SITOUT"),
                self.clearMoneyString(a.group("BOUNTY")),
            )

    def markStreets(self, hand: "Hand") -> None:
        """Reads player stack information from the hand text and updates the hand object.

        Extracts seat, player name, cash, sitout status, and bounty for each player before the summary section.

        Args:
            hand ("Hand"): The hand object to update with player stack information.

        Returns:
            None
        """
        # There is no marker between deal and draw in Stars single draw games
        #  this upsets the accounting, incorrectly sets handsPlayers.cardxx and
        #  in consequence the mucked-display is incorrect.
        # Attempt to fix by inserting a DRAW marker into the hand text attribute

        if hand.gametype["category"] in ("27_1draw", "fivedraw"):
            # isolate the first discard/stand pat line (thanks Carl for the regex)
            discard_split = re.split(
                r"(?:(.+(?: stands pat|: discards).+))",
                hand.handText,
                flags=re.DOTALL,
            )
            if len(hand.handText) != len(discard_split[0]):
                # DRAW street found, reassemble, with DRAW marker added
                discard_split[0] += "*** DRAW ***\r\n"
                hand.handText = ""
                for i in discard_split:
                    hand.handText += i

        # PREFLOP = ** Dealing down cards **
        # This re fails if,  say, river is missing; then we don't get the ** that starts the river.
        if hand.gametype["split"]:
            rit_pattern = (
                RIT_PREFLOP_PATTERN + RIT_FIRST_FLOP_PATTERN + RIT_SECOND_FLOP_PATTERN +
                RIT_FIRST_TURN_PATTERN + RIT_SECOND_TURN_PATTERN + RIT_FIRST_RIVER_PATTERN +
                RIT_SECOND_RIVER_PATTERN
            )
            m = re.search(rit_pattern, hand.handText, re.DOTALL)
        elif hand.gametype["base"] in ("hold"):
            if self.siteId == SITE_BOVADA:
                m = re.search(
                    r"\*\*\* HOLE CARDS \*\*\*(?P<PREFLOP>(.+(?P<FLOPET>\[\S\S\]))?.+(?=\*\*\* FLOP \*\*\*)|.+)"
                    r"(\*\*\* FLOP \*\*\*(?P<FLOP> (\[\S\S\] )?\[(\S\S ?)?\S\S \S\S\].+(?=\*\*\* TURN \*\*\*)|.+))?"
                    r"(\*\*\* TURN \*\*\* \[\S\S \S\S \S\S\] (?P<TURN>\[\S\S\].+(?=\*\*\* RIVER \*\*\*)|.+))?"
                    r"(\*\*\* RIVER \*\*\* \[\S\S \S\S \S\S\]? \[?\S\S\] (?P<RIVER>\[\S\S\].+))?",
                    hand.handText,
                    re.DOTALL,
                )
            else:
                pattern = (
                    PREFLOP_PATTERN + FLOP_PATTERN + TURN_PATTERN + RIVER_PATTERN +
                    FIRST_FLOP_PATTERN + FIRST_TURN_PATTERN + FIRST_RIVER_PATTERN +
                    SECOND_FLOP_PATTERN + SECOND_TURN_PATTERN + SECOND_RIVER_PATTERN
                )
                m = re.search(pattern, hand.handText, re.DOTALL)
        elif hand.gametype["base"] in ("stud"):
            m = re.search(
                r"(?P<ANTES>.+(?=\*\*\* 3rd STREET \*\*\*)|.+)"
                r"(\*\*\* 3rd STREET \*\*\*(?P<THIRD>.+(?=\*\*\* 4th STREET \*\*\*)|.+))?"
                r"(\*\*\* 4th STREET \*\*\*(?P<FOURTH>.+(?=\*\*\* 5th STREET \*\*\*)|.+))?"
                r"(\*\*\* 5th STREET \*\*\*(?P<FIFTH>.+(?=\*\*\* 6th STREET \*\*\*)|.+))?"
                r"(\*\*\* 6th STREET \*\*\*(?P<SIXTH>.+(?=\*\*\* RIVER \*\*\*)|.+))?"
                r"(\*\*\* RIVER \*\*\*(?P<SEVENTH>.+))?",
                hand.handText,
                re.DOTALL,
            )
        elif hand.gametype["base"] in ("draw"):
            if hand.gametype["category"] in ("27_1draw", "fivedraw"):
                m = re.search(
                    r"(?P<PREDEAL>.+(?=\*\*\* DEALING HANDS \*\*\*)|.+)"
                    r"(\*\*\* DEALING HANDS \*\*\*(?P<DEAL>.+(?=\*\*\* DRAW \*\*\*)|.+))?"
                    r"(\*\*\* DRAW \*\*\*(?P<DRAWONE>.+))?",
                    hand.handText,
                    re.DOTALL,
                )
            else:
                m = re.search(
                    r"(?P<PREDEAL>.+(?=\*\*\* DEALING HANDS \*\*\*)|.+)"
                    r"(\*\*\* DEALING HANDS \*\*\*(?P<DEAL>.+(?=\*\*\* FIRST DRAW \*\*\*)|.+))?"
                    r"(\*\*\* FIRST DRAW \*\*\*(?P<DRAWONE>.+(?=\*\*\* SECOND DRAW \*\*\*)|.+))?"
                    r"(\*\*\* SECOND DRAW \*\*\*(?P<DRAWTWO>.+(?=\*\*\* THIRD DRAW \*\*\*)|.+))?"
                    r"(\*\*\* THIRD DRAW \*\*\*(?P<DRAWTHREE>.+))?",
                    hand.handText,
                    re.DOTALL,
                )
        log.debug("type: %s, value: %s", type(m), m)
        mg = m.groupdict()
        log.debug("type mg: %s, value: %s", type(mg), mg)
        hand.addStreets(m)

    def readCommunityCards(
        self,
        hand: "Hand",
        street: str,
    ) -> None:
        """Reads and sets community cards for a given street in the hand.

        Extracts community cards from the hand text for the specified street and updates the hand object, handling run-it-twice scenarios.

        Args:
            hand ("Hand"): The hand object to update with community cards.
            street (str): The street name to extract community cards for.

        Returns:
            None

        Raises:
            FpdbHandPartial: If a blank community card is detected.
        """
        # street has been matched by markStreets, so exists in this hand
        if self.re_empty_card.search(hand.streets[street]):
            msg = "Blank community card"
            raise FpdbHandPartial(msg)
        if (
            street != "FLOPET" or hand.streets.get("FLOP") is None
        ):  # a list of streets which get dealt community cards (i.e. all but PREFLOP)
            if (m2 := self.re_board2.search(hand.streets[street])):
                hand.setCommunityCards(
                    street,
                    [m2.group("C1"), m2.group("C2"), m2.group("C3")],
                )
            else:
                m = self.re_board.search(hand.streets[street])
                hand.setCommunityCards(street, m.group("CARDS").split(" "))
        if street in {"FLOP1", "TURN1", "RIVER1", "FLOP2", "TURN2", "RIVER2"}:
            hand.runItTimes = 2

    def readSTP(self, hand: "Hand") -> None:
        """Reads STP (Side Pot) information from the hand text and updates the hand object.

        Searches for the STP amount in the hand text and adds it to the hand object if found.

        Args:
            hand ("Hand"): The hand object to update with STP information.

        Returns:
            None
        """
        if m := self.re_stp.search(hand.handText):
            hand.addSTP(m.group("AMOUNT"))

    def readAntes(self, hand: "Hand") -> None:
        """Reads ante information from the hand text and updates the hand object.

        Extracts ante amounts for each player and adds them to the hand object.

        Args:
            hand ("Hand"): The hand object to update with ante information.

        Returns:
            None
        """
        log.debug("reading antes")
        m = self.re_antes.finditer(hand.handText)
        for player in m:
            hand.addAnte(
                player.group("PNAME"),
                self.clearMoneyString(player.group("ANTE")),
            )

    def readBringIn(self, hand: "Hand") -> None:
        """Reads bring-in bet information from the hand text and updates the hand object.

        Searches for the bring-in bet in the hand text and adds it to the hand object if found.

        Args:
            hand ("Hand"): The hand object to update with bring-in information.

        Returns:
            None
        """
        if m := self.re_bring_in.search(hand.handText, re.DOTALL):
            hand.addBringIn(m.group("PNAME"), self.clearMoneyString(m.group("BRINGIN")))

    def readBlinds(self, hand: "Hand") -> None:
        """Reads blind and straddle information from the hand text and updates the hand object.

        Extracts small blind, big blind, dead blinds, straddle, and button blind postings from the hand text and adds them to the hand object.

        Args:
            hand ("Hand"): The hand object to update with blind information.

        Returns:
            None
        """
        live_blind = True
        for a in self.re_post_sb.finditer(hand.handText):
            if live_blind:
                hand.addBlind(
                    a.group("PNAME"),
                    "small blind",
                    self.clearMoneyString(a.group("SB")),
                )
                live_blind = False
            else:
                names = [p[1] for p in hand.players]
                if "Big Blind" in names or "Small Blind" in names or "Dealer" in names:
                    hand.addBlind(
                        a.group("PNAME"),
                        "small blind",
                        self.clearMoneyString(a.group("SB")),
                    )
                else:
                    # Post dead blinds as ante
                    hand.addBlind(
                        a.group("PNAME"),
                        "secondsb",
                        self.clearMoneyString(a.group("SB")),
                    )
        for a in self.re_post_bb.finditer(hand.handText):
            hand.addBlind(
                a.group("PNAME"),
                "big blind",
                self.clearMoneyString(a.group("BB")),
            )
        for a in self.re_post_both.finditer(hand.handText):
            hand.addBlind(
                a.group("PNAME"),
                "both",
                self.clearMoneyString(a.group("SBBB")),
            )
        for a in self.re_post_straddle.finditer(hand.handText):
            hand.addBlind(
                a.group("PNAME"),
                "straddle",
                self.clearMoneyString(a.group("STRADDLE")),
            )
        for a in self.re_post_bub.finditer(hand.handText):
            hand.addBlind(
                a.group("PNAME"),
                "button blind",
                self.clearMoneyString(a.group("BUB")),
            )

    def readHoleCards(self, hand: "Hand") -> None:
        """Reads and sets hole cards for each player from the hand text.

        Extracts hero and player hole cards for each street, handling special cases for stud games and updating the hand object accordingly.

        Args:
            hand ("Hand"): The hand object to update with hole card information.

        Returns:
            None
        """
        #    streets PREFLOP, PREDRAW, and THIRD are special cases beacause
        #    we need to grab hero's cards
        for street in ("PREFLOP", "DEAL"):
            if street in hand.streets:
                m = self.re_hero_cards.finditer(hand.streets[street])
                for found in m:
                    hand.hero = found.group("PNAME")
                    if "cards" not in found.group("NEWCARDS"):
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
            log.debug("text: %s", text)
            log.debug("hand.streets items: %s", list(hand.streets.items()))
            if not text or street in ("PREFLOP", "DEAL"):
                continue  # already done these

            m = self.re_hero_cards.finditer(hand.streets[street])
            for found in m:
                player = found.group("PNAME")
                newcards = [] if found.group("NEWCARDS") is None else found.group("NEWCARDS").split(" ")
                oldcards = [] if found.group("OLDCARDS") is None else found.group("OLDCARDS").split(" ")

                if street == "THIRD" and len(newcards) == STUD_HOLE_CARDS_COUNT:  # hero in stud game
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

    def _processAction(self, action: re.Match, hand: "Hand", street: str) -> None:
        """Processes a single betting action and updates the hand object.

        Interprets the action type and delegates to the appropriate hand method to record the action for the specified street.

        Args:
            action (re.Match): The regex match object containing action details.
            hand ("Hand"): The hand object to update with the action.
            street (str): The street name where the action occurred.

        Returns:
            None
        """
        atype = action["ATYPE"]
        pname = action["PNAME"]

        if atype == " folds":
            hand.addFold(street, pname)
        elif atype == " checks":
            hand.addCheck(street, pname)
        elif atype == " calls":
            hand.addCall(street, pname, self.clearMoneyString(action["BET"]))
        elif atype == " raises":
            self._processRaise(action, hand, street, pname)
        elif atype == " bets":
            hand.addBet(street, pname, self.clearMoneyString(action["BET"]))
        elif atype == " discards":
            hand.addDiscard(street, pname, action["BET"], action["CARDS"])
        elif atype == " stands pat":
            hand.addStandsPat(street, pname, action["CARDS"])
        else:
            log.debug("Unimplemented readAction: %r %r", pname, atype)

    def _processRaise(self, action: re.Match, hand: "Hand", street: str, pname: str) -> None:
        """Processes a raise action and updates the hand object.

        Determines the type of raise (to amount or call and raise) and records it for the specified street and player.

        Args:
            action (re.Match): The regex match object containing raise details.
            hand ("Hand"): The hand object to update with the raise action.
            street (str): The street name where the raise occurred.
            pname (str): The player name performing the raise.

        Returns:
            None
        """
        if action["BETTO"] is not None:
            hand.addRaiseTo(street, pname, self.clearMoneyString(action["BETTO"]))
        elif action["BET"] is not None:
            hand.addCallandRaise(street, pname, self.clearMoneyString(action["BET"]))

    def readAction(self, hand: "Hand", street: str) -> None:
        """Reads and processes betting actions for a given street in the hand.

        Extracts and records all player actions for the specified street, including folds, checks, calls, raises, bets, discards, and stands pat. Also detects and handles uncalled bets and walk scenarios.

        Args:
            hand ("Hand"): The hand object to update with action information.
            street (str): The street name to process actions for.

        Returns:
            None
        """
        s = f"{street}2" if hand.gametype["split"] and street in hand.communityStreets else street
        if not hand.streets[s]:
            return

        # Process all actions
        m = self.re_action.finditer(hand.streets[s])
        for action in m:
            self._processAction(action, hand, street)

        # Process uncalled bets
        if m := self.re_uncalled.search(hand.streets[s]):
            uncalled_player = m.group("PNAME").strip()  # Remove leading/trailing spaces
            uncalled_amount = m.group("BET")
            log.info("Processing uncalled bet: %s -> %s", uncalled_player, uncalled_amount)

            # Check if this could be a walk scenario by looking for collection by same player
            pre, post = hand.handText.split("*** SUMMARY ***")
            collection_match = self.re_collect_pot2.search(pre)
            if collection_match and collection_match.group("PNAME") == uncalled_player:
                collection_amount = Decimal(collection_match.group("POT").replace(",", ""))
                uncalled_decimal = Decimal(uncalled_amount.replace(",", ""))

                # Walk scenario detection:
                # 1. Same player has uncalled bet and collection
                # 2. Either: uncalled == collection (rare case, e.g., heads-up)
                #    Or: uncalled > collection (typical walk: BB gets SB, BB returned)
                if uncalled_decimal == collection_amount:
                    log.info(
                        "True walk scenario detected (equal): %s uncalled=%s collected=%s",
                        uncalled_player, uncalled_amount, collection_amount,
                    )
                    if not hasattr(hand, "walk_adjustments"):
                        hand.walk_adjustments = {}
                    hand.walk_adjustments[uncalled_player] = uncalled_decimal
                elif uncalled_decimal > collection_amount:
                    # This is likely a BB walk: BB gets only SB contribution, BB bet returned
                    log.info(
                        "True walk scenario detected (BB walk): %s uncalled=%s collected=%s",
                        uncalled_player, uncalled_amount, collection_amount,
                    )
                    if not hasattr(hand, "walk_adjustments"):
                        hand.walk_adjustments = {}
                    hand.walk_adjustments[uncalled_player] = uncalled_decimal
                else:
                    log.info(
                        "Not a walk - uncalled bet (%s) < collection (%s) for %s",
                        uncalled_amount, collection_amount, uncalled_player,
                    )

            hand.addUncalled(street, uncalled_player, uncalled_amount)

    def readShowdownActions(self, hand: "Hand") -> None:
        """Reads showdown actions from the hand text and updates the hand object.

        Extracts shown cards for each player at showdown and adds them to the hand object.

        Args:
            hand ("Hand"): The hand object to update with showdown card information.

        Returns:
            None
        """
        # TODO(@fpdb): pick up mucks also??
        for shows in self.re_showdown_action.finditer(hand.handText):
            cards = shows.group("CARDS").split(" ")
            hand.addShownCards(cards, shows.group("PNAME"))

    def _processProgressiveBounties(self, hand: "Hand") -> None:
        """Processes progressive knockout bounties and updates the hand object.

        Calculates progressive bounty amounts for each player, sets end bounty values, and updates the hand's progressive status and koCounts.

        Args:
            hand ("Hand"): The hand object to update with progressive bounty information.

        Returns:
            None
        """
        ko_amounts = {}

        for a in self.re_progressive.finditer(hand.handText):
            if a.group("PNAME") not in ko_amounts:
                ko_amounts[a.group("PNAME")] = 0
            ko_amounts[a.group("PNAME")] += 100 * float(a.group("AMT"))
            hand.endBounty[a.group("PNAME")] = 100 * float(a.group("ENDAMT"))
            hand.isProgressive = True

        if hand.koBounty > 0:
            m = self.re_winning_rank_one.search(hand.handText)
            winner = m.group("PNAME") if m else None
            
            for pname, amount in list(ko_amounts.items()):
                if pname == winner:
                    hand.koCounts[pname] = (amount + hand.endBounty[pname]) / float(hand.koBounty)
                else:
                    hand.koCounts[pname] = amount / float(hand.koBounty)

    def _processRegularBounties(self, hand: "Hand") -> None:
        """Processes regular knockout bounties and updates the hand object.

        Iterates through bounty matches in the hand text, handling split and single bounties, and updates the koCounts for each player.

        Args:
            hand ("Hand"): The hand object to update with regular bounty information.

        Returns:
            None
        """
        for a in self.re_bounty.finditer(hand.handText):
            if a["SPLIT"] == "split":
                self._processSplitBounty(hand, a)
            else:
                self._processSingleBounty(hand, a)

    def _processSplitBounty(self, hand: "Hand", match: re.Match) -> None:
        """Processes split knockout bounties and updates the hand object.

        Splits the bounty among multiple players listed in the match and updates their koCounts accordingly.

        Args:
            hand ("Hand"): The hand object to update with split bounty information.
            match (re.Match): The regex match object containing player names.

        Returns:
            None
        """
        pnames = match["PNAME"].split(", ")
        for pname in pnames:
            if pname not in hand.koCounts:
                hand.koCounts[pname] = 0
            hand.koCounts[pname] += 1 / float(len(pnames))

    def _processSingleBounty(self, hand: "Hand", match: re.Match) -> None:
        """Processes a single knockout bounty and updates the hand object.

        Increments the koCounts for the player listed in the match to reflect a single bounty win.

        Args:
            hand ("Hand"): The hand object to update with single bounty information.
            match (re.Match): The regex match object containing the player name.

        Returns:
            None
        """
        pname = match["PNAME"]
        if pname not in hand.koCounts:
            hand.koCounts[pname] = 0
        hand.koCounts[pname] += 1

    def readTourneyResults(self, hand: "Hand") -> None:
        """Reads tournament results and updates bounty information for the hand.

        Determines whether the hand contains progressive or regular bounties and processes them accordingly to update player KO counts.

        Args:
            hand ("Hand"): The hand object to update with tournament results.

        Returns:
            None
        """
        if self.re_bounty.search(hand.handText) is None:
            self._processProgressiveBounties(hand)
        else:
            self._processRegularBounties(hand)

    def _calculateBovadaAdjustments(self, hand: "Hand") -> tuple[bool, bool, float, float]:
        """Calculates Bovada-specific adjustments for pot collection scenarios.

        Determines if a hand contains Bovada walk scenarios and calculates necessary adjustments for blinds and pot amounts.

        Args:
            hand ("Hand"): The hand object to analyze for Bovada adjustments.

        Returns:
            tuple[bool, bool, float, float]: Flags and adjustment values for Bovada walk scenarios.
        """
        acts = hand.actions.get("PREFLOP")
        bovada_uncalled_v1, bovada_uncalled_v2, blindsantes, adjustment = False, False, 0, 0

        names = [p[1] for p in hand.players]
        if (
            ("Big Blind" in names or "Small Blind" in names or "Dealer" in names or self.siteId == SITE_MERGE)
            and acts is not None
            and all(a[1] == "folds" for a in acts)
        ):
            m0 = self.re_uncalled.search(hand.handText)
            if m0 and float(m0.group("BET")) == float(hand.bb):
                bovada_uncalled_v2 = True
            elif m0 is None:
                bovada_uncalled_v1 = True
                has_sb = any(a[1] == "small blind" for a in hand.actions.get("BLINDSANTES"))
                adjustment = (float(hand.bb) - float(hand.sb)) if has_sb else float(hand.bb)
                blindsantes = sum(a[2] for a in hand.actions.get("BLINDSANTES"))

        return bovada_uncalled_v1, bovada_uncalled_v2, blindsantes, adjustment

    def _addCollectPotWithAdjustment(
        self,
        hand: "Hand",
        match: re.Match,
        adjustments: tuple[bool, bool, float, float],
    ) -> None:
        """Adds pot collection information to the hand object, applying Bovada-specific adjustments.

        Adjusts the collected pot amount for Bovada walk scenarios and updates the hand object with the correct value.

        Args:
            hand ("Hand"): The hand object to update with pot collection information.
            match (re.Match): The regex match object containing pot and player details.
            adjustments (tuple[bool, bool, float, float]): Flags and adjustment values for Bovada walk scenarios.

        Returns:
            None
        """
        bovada_uncalled_v1, bovada_uncalled_v2, blindsantes, adjustment = adjustments
        pot = self.clearMoneyString(match["POT"])
        player = match["PNAME"]

        if bovada_uncalled_v1 and float(pot) == (blindsantes + hand.pot.stp):
            hand.addCollectPot(player=player, pot=str(float(pot) - adjustment))
        elif bovada_uncalled_v2:
            hand.addCollectPot(player=player, pot=str(float(pot) * 2))
        else:
            hand.addCollectPot(player=player, pot=pot)

    def readCollectPot(self, hand: "Hand") -> None:
        """Reads pot collection information from the hand text and updates the hand object.

        Processes all pot collections for the hand, applying Bovada-specific adjustments and handling walk scenarios and cash out fees.

        Args:
            hand ("Hand"): The hand object to update with pot collection information.

        Returns:
            None
        """
        # Bovada walks are calculated incorrectly in converted PokerStars hands
        adjustments = self._calculateBovadaAdjustments(hand)

        i = 0
        pre, post = hand.handText.split("*** SUMMARY ***")
        hand.cashedOut = self.re_cashed_out.search(pre) is not None

        # Walk scenarios are already detected in readAction

        if hand.runItTimes == 0 and not hand.cashedOut:
            for m in self.re_collect_pot.finditer(post):
                self._addCollectPotWithAdjustment(hand, m, adjustments)
                i += 1

        if i == 0:
            log.info("Processing collections from pre-summary section")
            for m in self.re_collect_pot2.finditer(pre):
                player = m.group("PNAME")
                pot_amount = Decimal(m.group("POT").replace(",", ""))
                log.info("Found collection: %s -> %s", player, pot_amount)

                # Check if this is a walk scenario (already detected in readAction)
                if hasattr(hand, "walk_adjustments") and player in hand.walk_adjustments:
                    log.info("Walk scenario confirmed for %s", player)

                self._addCollectPotWithAdjustment(hand, m, adjustments)
                i += 1
            
            # Handle cash out with fee pattern
            for m in self.re_collect_pot3.finditer(pre):
                player = m.group("PNAME")
                pot_amount = Decimal(m.group("POT").replace(",", ""))
                fee_amount = Decimal(m.group("FEE").replace(",", ""))
                log.info("Found cash out collection: %s -> %s (fee: %s)", player, pot_amount, fee_amount)
                
                # Store cash out fee information for statistics/logging
                # Fee is not added to collected pot as it's taken by the site
                if not hasattr(hand, 'cashOutFees'):
                    hand.cashOutFees = {}
                hand.cashOutFees[player] = fee_amount
                
                self._addCollectPotWithAdjustment(hand, m, adjustments)
                i += 1

    def readShownCards(self, hand: "Hand") -> None:
        """Reads shown and mucked cards from the hand text and updates the hand object.

        Extracts revealed cards for each player, including shown and mucked cards, and adds them to the hand object with appropriate flags.

        Args:
            hand ("Hand"): The hand object to update with shown and mucked card information.

        Returns:
            None
        """
        if self.siteId == SITE_MERGE:
            re_revealed_cards = re.compile(
                r"Dealt to {PLYR}(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])".format(**self.substitutions),
                re.MULTILINE,
            )
            m = re_revealed_cards.finditer(hand.handText)
            for found in m:
                cards = found.group("NEWCARDS").split(" ")
                hand.addShownCards(
                    cards=cards,
                    player=found.group("PNAME"),
                    shown=True,
                    mucked=False,
                )

        for m in self.re_shown_cards.finditer(hand.handText):
            if m.group("CARDS") is not None:
                cards = m.group("CARDS")
                cards = cards.split(
                    " ",
                )  # needs to be a list, not a set--stud needs the order
                string = m.group("STRING")
                if m.group("STRING2"):
                    string += "|" + m.group("STRING2")

                (shown, mucked) = (False, False)
                if m.group("SHOWED") == "showed":
                    shown = True
                elif m.group("SHOWED") == "mucked":
                    mucked = True

                # print "DEBUG: hand.addShownCards(%s, %s, %s, %s)" %(cards, m.group('PNAME'), shown, mucked)
                hand.addShownCards(
                    cards=cards,
                    player=m.group("PNAME"),
                    shown=shown,
                    mucked=mucked,
                    string=string,
                )

    def _parseRakeAndPot(self, hand: "Hand") -> None:
        """Parses rake and total pot information from the hand text and updates the hand object.

        Searches for explicit rake and pot values in the summary section, parses them, and sets them on the hand object. Marks rake as parsed to avoid recalculation.

        Args:
            hand ("Hand"): The hand object to update with rake and pot information.

        Returns:
            None
        """
        # Look for rake information in the summary section
        if rake_match := self.re_rake.search(hand.handText):
            # Extract pot and rake values
            total_pot_str = rake_match.group("POT").replace(",", "")
            rake_str = rake_match.group("RAKE").replace(",", "")

            try:
                total_pot, rake = self._parse_decimal_values(total_pot_str, rake_str)

                # Set the values on the hand object
                hand.totalpot = total_pot
                hand.rake = rake

                log.info("Parsed from hand text: Total pot=%s, Rake=%s", total_pot, rake)

                # Mark that rake was explicitly parsed (to avoid recalculation)
                hand.rake_parsed = True

            except (ValueError, TypeError) as e:
                log.warning("Failed to parse rake/pot values: %s", e)
        else:
            log.debug("No explicit rake information found in hand text")

    def _parse_decimal_values(self, total_pot_str: str, rake_str: str) -> tuple[Decimal, Decimal]:
        """Parses string representations of total pot and rake into Decimal values.

        Converts the provided pot and rake strings to Decimal objects for accurate financial calculations.

        Args:
            total_pot_str (str): String representation of the total pot amount.
            rake_str (str): String representation of the rake amount.

        Returns:
            tuple[Decimal, Decimal]: The total pot and rake as Decimal values.
        """
        total_pot = Decimal(total_pot_str)
        rake = Decimal(rake_str)
        return total_pot, rake

    def readSummaryInfo(self, summary_info_list: list[str]) -> bool:  # noqa: ARG002
        """Implement the abstract method from HandHistoryConverter."""
        # Add the actual implementation here, or use a placeholder if not needed
        log.info("Reading summary info for PokerStars.")
        return True

    @staticmethod
    def getTableTitleRe(
        game_type: str,
        table_name: str | None = None,
        tournament: str | None = None,
        table_number: str | None = None,
    ) -> str:
        """Generates a regular expression for matching PokerStars table titles.

        Returns a regex string for cash game or tournament table titles based on the provided game type and identifiers.

        Args:
            game_type (str): The type of game ("ring" or "tour").
            table_name (str | None): The name of the table for cash games.
            tournament (str | None): The tournament name for tournament games.
            table_number (str | None): The table number for tournament games.

        Returns:
            str: The regular expression string for matching table titles.
        """
        regex = re.escape(str(table_name))
        log.debug("Regex for cash game: %s", regex)

        if game_type == "tour":
            regex = f"{re.escape(str(tournament))} (Table|Tisch) {re.escape(str(table_number))}"
            log.debug("Regex for tournament: %s", regex)
            log.info(
                "Stars table_name=%r, tournament=%r, table_number=%r",
                table_name, tournament, table_number,
            )
            log.info("Stars returns: %r", regex)

        return regex
