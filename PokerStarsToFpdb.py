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
        r"{PLYR} (collected|cashed out the hand for) {CUR}(?P<POT>[,.\d]+)".format(**substitutions),
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
        """Load hero -> skins mappings from the configuration file."""
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
        """Detect skin based on hero name mapping."""
        hero_match = re.search(r"Dealt to ([^\[]+)", hand_text[:500])
        if not hero_match:
            return None

        hero_name = hero_match.group(1).strip()

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
        """Detect skin based on file path patterns."""
        # Normalise the path for comparison
        path_lower = file_path.lower().replace("\\", "/")

        # Search for typical path patterns for each skin
        for pattern, skin_name in POKERSTARS_PATH_PATTERNS:
            if pattern in path_lower:
                return skin_name, POKERSTARS_SKIN_IDS[skin_name]
        return None

    def detectPokerStarsSkin(self, hand_text: str, file_path: str | None = None) -> tuple[str, int]:
        """Detects specific PokerStars skin based on file path and/or content."""
        # First, check whether the hero has a mapping configured
        hero_result = self._detectSkinByHero(hand_text)
        if hero_result:
            return hero_result

        # Then try to detect the path
        if file_path:
            path_result = self._detectSkinByPath(file_path)
            if path_result:
                return path_result

        # Finally, analyze content
        return self._detectSkinByContent(hand_text)

    def _detectSkinByContent(self, hand_text: str) -> tuple[str, int]:
        """Detect skin based on hand text content."""
        search_text = hand_text[:2000]

        # Verification of AAMS/ADM ID for Italy
        if "AAMS ID:" in search_text or "ADM ID:" in search_text:
            return "PokerStars.IT", SITE_POKERSTARS_IT

        # Try to detect via hero name if it contains clues
        hero_match = re.search(r"Dealt to ([^\[]+)", hand_text[:500])
        if hero_match:
            hero_name = hero_match.group(1).strip()
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

        for regex, skin_name in regex_tests:
            if regex.search(search_text):
                return skin_name, POKERSTARS_SKIN_IDS[skin_name]

        # As a last resort, use the currency
        if "€" in search_text or "EUR" in search_text:
            return "PokerStars.EU", SITE_POKERSTARS_EU
        # The default setting is PokerStars.COM
        return "PokerStars.COM", SITE_POKERSTARS_COM

    def readOther(self, hand: "Hand") -> None:
        """Read other information from hand text."""

    def allHandsAsList(self) -> list[str]:
        """Override parent method to clean up PokerStars archive formats."""
        # Call parent implementation first
        handlist = super().allHandsAsList()

        # Log what we got
        log.info("PokerStars allHandsAsList: got %d hands", len(handlist))

        # Clean up archive formats if detected
        cleaned_handlist = []
        for i, hand_text in enumerate(handlist):
            log.debug("Processing hand %d/%d", i+1, len(handlist))
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
                cleaned_text = "\n".join(cleaned_lines).strip()
                if cleaned_text:  # Only add non-empty hands
                    cleaned_handlist.append(cleaned_text)
            else:
                cleaned_handlist.append(hand_text)

        log.info("PokerStars allHandsAsList: returning %d cleaned hands", len(cleaned_handlist))
        return cleaned_handlist

    def compilePlayerRegexs(self, hand: "Hand") -> None:
        """Compile regex patterns for all players in the hand."""
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

    def _parseBasicGameInfo(self, mg: dict) -> dict[str, str]:
        """Parse basic game information from regex groups."""
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
        """Parse game flags from regex groups."""
        flags = {}

        flags["fast"] = "Zoom" in mg["TITLE"] or "Rush" in mg["TITLE"]
        flags["homeGame"] = "Home" in mg["TITLE"]
        flags["split"] = "SPLIT" in mg and mg["SPLIT"] == "Split"

        if "CAP" in mg and mg["CAP"] is not None:
            flags["buyinType"] = "cap"
        else:
            flags["buyinType"] = "regular"

        return flags

    def _detectSiteType(self, mg: dict, hand_text: str, info: dict) -> None:
        """Detect and set site type information."""
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
        elif mg["SITE"] == "PokerStars" or mg["SITE"] == "POKERSTARS":
            # Detection of specific PokerStars skin
            self.sitename, self.site_id = self.detectPokerStarsSkin(
                hand_text,
                self.in_path if hasattr(self, "in_path") else None,
            )

    def determineGameType(self, hand_text: str) -> dict[str, str]:
        """Parse hand text to determine game type information."""
        m = self.re_game_info.search(hand_text)
        if not m:
            tmp = hand_text[0:200]
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
        """Determine if this is a tournament or ring game."""
        if "TOURNO" in mg and mg["TOURNO"] is None:
            info["type"] = "ring"
        else:
            info["type"] = "tour"
            if "ZOOM" in mg["TOUR"]:
                info["fast"] = True

    def _adjustCurrencyAndBlinds(self, mg: dict, info: dict, hand_text: str) -> None:
        """Adjust currency and blind values based on game type."""
        if info.get("currency") in ("T$", None) and info["type"] == "ring":
            info["currency"] = "play"

        if info["limitType"] == "fl" and info["bb"] is not None:
            if info["type"] == "ring":
                try:
                    info["sb"] = self.lim_blinds[mg["BB"]][0]
                    info["bb"] = self.lim_blinds[mg["BB"]][1]
                except KeyError:
                    tmp = hand_text[0:200]
                    log.exception("Lim_Blinds has no lookup for %r - %r", mg["BB"], tmp)
                    raise FpdbParseError from None
            else:
                sb_decimal = Decimal(mg["SB"]) / 2
                bb_decimal = Decimal(mg["SB"])
                info["sb"] = str(sb_decimal.quantize(Decimal("0.01")))
                info["bb"] = str(bb_decimal.quantize(Decimal("0.01")))

    def _processDateTime(self, datetime_str: str, hand: "Hand") -> None:
        """Process datetime information from hand text."""
        # 2008/11/12 10:00:48 CET [2008/11/12 4:00:48 ET]
        # (both dates are parsed so ET date overrides the other)
        # 2008/08/17 - 01:14:43 (ET)
        # 2008/09/07 06:23:14 ET
        datetimestr = "2000/01/01 00:00:00"  # default used if time not found

        if self.siteId == SITE_MERGE:
            m2 = self.re_date_time2.finditer(datetime_str)
            for a in m2:
                datetimestr = "{}/{}/{} {}:{}:{}".format(
                    a.group("Y"),
                    a.group("M"),
                    a.group("D"),
                    a.group("H"),
                    a.group("MIN"),
                    "00",
                )
            hand.startTime = datetime.datetime.strptime(  # noqa: DTZ007
                datetimestr,
                "%Y/%m/%d %H:%M:%S",
            )  # timezone handled by changeTimezone below
        else:
            m1 = self.re_date_time1.finditer(datetime_str)
            for a in m1:
                datetimestr = "{}/{}/{} {}:{}:{}".format(
                    a.group("Y"),
                    a.group("M"),
                    a.group("D"),
                    a.group("H"),
                    a.group("MIN"),
                    a.group("S"),
                )
            hand.startTime = datetime.datetime.strptime(  # noqa: DTZ007
                datetimestr,
                "%Y/%m/%d %H:%M:%S",
            )  # timezone handled by changeTimezone below
            hand.startTime = HandHistoryConverter.changeTimezone(
                hand.startTime,
                "ET",
                "UTC",
            )

    def _processBuyinInfo(self, info: dict, hand: "Hand") -> None:
        """Process tournament buyin information."""
        key = "BUYIN"
        if info[key].strip() == "Freeroll":
            hand.buyin = 0
            hand.fee = 0
            hand.buyinCurrency = "FREE"
        elif info[key].strip() == "":
            hand.buyin = 0
            hand.fee = 0
            hand.buyinCurrency = "NA"
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
        """Detect currency from buyin string."""
        if buyin_str.find("$") != -1:
            hand.buyinCurrency = "USD"
        elif buyin_str.find("£") != -1:
            hand.buyinCurrency = "GBP"
        elif buyin_str.find("€") != -1:
            hand.buyinCurrency = "EUR"
        elif buyin_str.find("₹") != -1 or buyin_str.find("Rs. ") != -1:
            hand.buyinCurrency = "INR"
        elif buyin_str.find("¥") != -1:
            hand.buyinCurrency = "CNY"
        elif buyin_str.find("FPP") != -1 or buyin_str.find("SC") != -1:
            hand.buyinCurrency = "PSFP"
        elif re.match("[0-9+]*$", buyin_str.strip()):
            hand.buyinCurrency = "play"
        else:
            log.error("Failed to detect currency. Hand ID: %s: %r", hand.handid, buyin_str)
            raise FpdbParseError

    def _processBountyAndFees(self, info: dict, hand: "Hand") -> None:
        """Process bounty and fee information."""
        if hand.buyinCurrency != "PSFP":
            if info["BOUNTY"] is not None:
                # There is a bounty, which means we need to switch BOUNTY and BIRAKE values
                tmp = info["BOUNTY"]
                info["BOUNTY"] = info["BIRAKE"]
                info["BIRAKE"] = tmp
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
        """Process all hand information from parsed data."""
        for key in info:
            self._processHandInfoKey(key, info, hand)

    def _processHandInfoKey(self, key: str, info: dict, hand: "Hand") -> None:
        """Process a single key from hand info data."""
        if key in ("DATETIME", "HID", "TOURNO"):
            self._processBasicHandFields(key, info, hand)
        elif key in ("BUYIN", "LEVEL", "SHOOTOUT"):
            self._processTournamentFields(key, info, hand)
        elif key in ("TABLE", "BUTTON", "MAX"):
            self._processTableFields(key, info, hand)

    def _processBasicHandFields(self, key: str, info: dict, hand: "Hand") -> None:
        """Process basic hand identification fields."""
        if key == "DATETIME":
            self._processDateTime(info[key], hand)
        elif key == "HID":
            hand.handid = info[key]
        elif key == "TOURNO" and info[key] is not None:
            hand.tourNo = info[key][-18:]

    def _processTournamentFields(self, key: str, info: dict, hand: "Hand") -> None:
        """Process tournament-specific fields."""
        if key == "BUYIN" and hand.tourNo is not None:
            self._processBuyinInfo(info, hand)
        elif key == "LEVEL":
            hand.level = info[key]
        elif key == "SHOOTOUT" and info[key] is not None:
            hand.isShootout = True

    def _processTableFields(self, key: str, info: dict, hand: "Hand") -> None:
        """Process table-related fields."""
        if key == "TABLE":
            self._processTableInfo(info, hand)
        elif key == "BUTTON":
            hand.buttonpos = info[key]
        elif key == "MAX" and info[key] is not None:
            hand.maxseats = int(info[key])

    def _processTableInfo(self, info: dict, hand: "Hand") -> None:
        """Process table name information."""
        tablesplit = re.split(" ", info["TABLE"])
        if info["TOURNO"] is not None and info["HIVETABLE"] is not None:
            hand.tablename = info["HIVETABLE"]
        elif hand.tourNo is not None and len(tablesplit) > 1:
            hand.tablename = tablesplit[1]
        else:
            hand.tablename = info["TABLE"]

    def readHandInfo(self, hand: "Hand") -> None:
        """Extract hand information from hand text."""
        # First check if partial
        if hand.handText.count("*** SUMMARY ***") != 1:
            msg = "Hand is not cleanly split into pre and post Summary"
            raise FpdbHandPartial(
                (msg),
            )

        info = {}
        m = self.re_hand_info.search(hand.handText, re.DOTALL)
        m2 = self.re_game_info.search(hand.handText)
        if m is None or m2 is None:
            tmp = hand.handText[0:200]
            log.error("read Hand Info failed: %r", tmp)
            raise FpdbParseError

        info.update(m.groupdict())
        info.update(m2.groupdict())

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
        """Identify the dealer button position."""
        m = self.re_button.search(hand.handText)
        if m:
            hand.buttonpos = int(m.group("BUTTON"))
        else:
            log.info("readButton: not found")

    def readPlayerStacks(self, hand: "Hand") -> None:
        """Extract player stack sizes and positions."""
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
        """Mark street boundaries in hand text."""
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
            if len(hand.handText) == len(discard_split[0]):
                # hand_text was not split, no DRAW street occurred
                pass
            else:
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
        """Read community cards for each street."""  # street has been matched by markStreets, so exists in this hand
        if self.re_empty_card.search(hand.streets[street]):
            msg = "Blank community card"
            raise FpdbHandPartial(msg)
        if (
            street != "FLOPET" or hand.streets.get("FLOP") is None
        ):  # a list of streets which get dealt community cards (i.e. all but PREFLOP)
            m2 = self.re_board2.search(hand.streets[street])
            if m2:
                hand.setCommunityCards(
                    street,
                    [m2.group("C1"), m2.group("C2"), m2.group("C3")],
                )
            else:
                m = self.re_board.search(hand.streets[street])
                hand.setCommunityCards(street, m.group("CARDS").split(" "))
        if street in ("FLOP1", "TURN1", "RIVER1", "FLOP2", "TURN2", "RIVER2"):
            hand.runItTimes = 2

    def readSTP(self, hand: "Hand") -> None:
        """Read Splash the Pot information."""
        m = self.re_stp.search(hand.handText)
        if m:
            hand.addSTP(m.group("AMOUNT"))

    def readAntes(self, hand: "Hand") -> None:
        """Extract ante information from hand text."""
        log.debug("reading antes")
        m = self.re_antes.finditer(hand.handText)
        for player in m:
            hand.addAnte(
                player.group("PNAME"),
                self.clearMoneyString(player.group("ANTE")),
            )

    def readBringIn(self, hand: "Hand") -> None:
        """Extract bring-in bet information."""
        m = self.re_bring_in.search(hand.handText, re.DOTALL)
        if m:
            hand.addBringIn(m.group("PNAME"), self.clearMoneyString(m.group("BRINGIN")))

    def readBlinds(self, hand: "Hand") -> None:
        """Extract blind bet information."""
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
        """Extract hole cards for all players."""
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

    def _processAction(self, action: re.Match, hand: "Hand", street: str) -> None:
        """Process a single poker action."""
        atype = action.group("ATYPE")
        pname = action.group("PNAME")

        if atype == " folds":
            hand.addFold(street, pname)
        elif atype == " checks":
            hand.addCheck(street, pname)
        elif atype == " calls":
            hand.addCall(street, pname, self.clearMoneyString(action.group("BET")))
        elif atype == " raises":
            self._processRaise(action, hand, street, pname)
        elif atype == " bets":
            hand.addBet(street, pname, self.clearMoneyString(action.group("BET")))
        elif atype == " discards":
            hand.addDiscard(street, pname, action.group("BET"), action.group("CARDS"))
        elif atype == " stands pat":
            hand.addStandsPat(street, pname, action.group("CARDS"))
        else:
            log.debug("Unimplemented readAction: %r %r", pname, atype)

    def _processRaise(self, action: re.Match, hand: "Hand", street: str, pname: str) -> None:
        """Process a raise action."""
        if action.group("BETTO") is not None:
            hand.addRaiseTo(street, pname, self.clearMoneyString(action.group("BETTO")))
        elif action.group("BET") is not None:
            hand.addCallandRaise(street, pname, self.clearMoneyString(action.group("BET")))

    def readAction(self, hand: "Hand", street: str) -> None:
        """Parse betting actions for a specific street."""
        s = street + "2" if hand.gametype["split"] and street in hand.communityStreets else street
        if not hand.streets[s]:
            return

        # Process all actions
        m = self.re_action.finditer(hand.streets[s])
        for action in m:
            self._processAction(action, hand, street)

        # Process uncalled bets
        m = self.re_uncalled.search(hand.streets[s])
        if m:
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
        """Extract showdown actions and revealed cards."""
        # TODO(@fpdb): pick up mucks also??
        for shows in self.re_showdown_action.finditer(hand.handText):
            cards = shows.group("CARDS").split(" ")
            hand.addShownCards(cards, shows.group("PNAME"))

    def _processProgressiveBounties(self, hand: "Hand") -> None:
        """Process progressive knockout bounties."""
        ko_amounts = {}
        winner = None

        for a in self.re_progressive.finditer(hand.handText):
            if a.group("PNAME") not in ko_amounts:
                ko_amounts[a.group("PNAME")] = 0
            ko_amounts[a.group("PNAME")] += 100 * float(a.group("AMT"))
            hand.endBounty[a.group("PNAME")] = 100 * float(a.group("ENDAMT"))
            hand.isProgressive = True

        m = self.re_winning_rank_one.search(hand.handText)
        if m:
            winner = m.group("PNAME")

        if hand.koBounty > 0:
            for pname, amount in list(ko_amounts.items()):
                if pname == winner:
                    hand.koCounts[pname] = (amount + hand.endBounty[pname]) / float(hand.koBounty)
                else:
                    hand.koCounts[pname] = amount / float(hand.koBounty)

    def _processRegularBounties(self, hand: "Hand") -> None:
        """Process regular knockout bounties."""
        for a in self.re_bounty.finditer(hand.handText):
            if a.group("SPLIT") == "split":
                self._processSplitBounty(hand, a)
            else:
                self._processSingleBounty(hand, a)

    def _processSplitBounty(self, hand: "Hand", match: re.Match) -> None:
        """Process a split bounty between multiple players."""
        pnames = match.group("PNAME").split(", ")
        for pname in pnames:
            if pname not in hand.koCounts:
                hand.koCounts[pname] = 0
            hand.koCounts[pname] += 1 / float(len(pnames))

    def _processSingleBounty(self, hand: "Hand", match: re.Match) -> None:
        """Process a single player bounty."""
        pname = match.group("PNAME")
        if pname not in hand.koCounts:
            hand.koCounts[pname] = 0
        hand.koCounts[pname] += 1

    def readTourneyResults(self, hand: "Hand") -> None:
        """Reads knockout bounties and add them to the koCounts dict."""
        if self.re_bounty.search(hand.handText) is None:
            self._processProgressiveBounties(hand)
        else:
            self._processRegularBounties(hand)

    def _calculateBovadaAdjustments(self, hand: "Hand") -> tuple[bool, bool, float, float]:
        """Calculate Bovada-specific adjustments for walks."""
        acts = hand.actions.get("PREFLOP")
        bovada_uncalled_v1, bovada_uncalled_v2, blindsantes, adjustment = False, False, 0, 0

        names = [p[1] for p in hand.players]
        if (
            ("Big Blind" in names or "Small Blind" in names or "Dealer" in names or self.siteId == SITE_MERGE)
            and acts is not None
            and len([a for a in acts if a[1] != "folds"]) == 0
        ):
            m0 = self.re_uncalled.search(hand.handText)
            if m0 and float(m0.group("BET")) == float(hand.bb):
                bovada_uncalled_v2 = True
            elif m0 is None:
                bovada_uncalled_v1 = True
                has_sb = len([a[2] for a in hand.actions.get("BLINDSANTES") if a[1] == "small blind"]) > 0
                adjustment = (float(hand.bb) - float(hand.sb)) if has_sb else float(hand.bb)
                blindsantes = sum([a[2] for a in hand.actions.get("BLINDSANTES")])

        return bovada_uncalled_v1, bovada_uncalled_v2, blindsantes, adjustment

    def _addCollectPotWithAdjustment(
        self,
        hand: "Hand",
        match: re.Match,
        adjustments: tuple[bool, bool, float, float],
    ) -> None:
        """Add collect pot with Bovada adjustments."""
        bovada_uncalled_v1, bovada_uncalled_v2, blindsantes, adjustment = adjustments
        pot = self.clearMoneyString(match.group("POT"))
        player = match.group("PNAME")

        if bovada_uncalled_v1 and float(pot) == (blindsantes + hand.pot.stp):
            hand.addCollectPot(player=player, pot=str(float(pot) - adjustment))
        elif bovada_uncalled_v2:
            hand.addCollectPot(player=player, pot=str(float(pot) * 2))
        else:
            hand.addCollectPot(player=player, pot=pot)

    def readCollectPot(self, hand: "Hand") -> None:
        """Extract pot collection information."""
        # Bovada walks are calculated incorrectly in converted PokerStars hands
        adjustments = self._calculateBovadaAdjustments(hand)

        i = 0
        pre, post = hand.handText.split("*** SUMMARY ***")
        hand.cashedOut = self.re_cashed_out.search(pre) is not None

        # Walk scenarios are already detected in readAction

        if hand.runItTimes == 0 and hand.cashedOut is False:
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

    def readShownCards(self, hand: "Hand") -> None:
        """Parse cards shown at showdown."""
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
        """Parse rake and total pot information from hand text if available."""
        # Look for rake information in the summary section
        rake_match = self.re_rake.search(hand.handText)
        if rake_match:
            # Extract pot and rake values
            total_pot_str = rake_match.group("POT").replace(",", "")
            rake_str = rake_match.group("RAKE").replace(",", "")

            try:
                total_pot = Decimal(total_pot_str)
                rake = Decimal(rake_str)

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
        """Returns string to search in windows titles."""
        regex = re.escape(str(table_name))
        log.debug("Regex for cash game: %s", regex)

        if game_type == "tour":
            regex = re.escape(str(tournament)) + " (Table|Tisch) " + re.escape(str(table_number))
            log.debug("Regex for tournament: %s", regex)
            log.info(
                "Stars table_name=%r, tournament=%r, table_number=%r",
                table_name, tournament, table_number,
            )
            log.info("Stars returns: %r", regex)

        return regex
