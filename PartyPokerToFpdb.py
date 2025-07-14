#!/usr/bin/env python
#
#    Copyright 2009-2011, Grigorij Indigirkin
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
import time
from decimal import Decimal

import Database
from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger
from TourneySummary import TourneySummary

# Obtention du logger configuré
log = get_logger("parser")


class PartyPoker(HandHistoryConverter):
    sitename = "PartyPoker"
    codepage = ("utf8", "cp1252")
    siteId = 9
    filetype = "text"
    sym = {"USD": r"\$", "EUR": "\u20ac", "T$": "", "play": "play"}
    currencies = {
        r"\$": "USD",
        "$": "USD",
        "\xe2\x82\xac": "EUR",
        "\u20ac": "EUR",
        "": "T$",
        "play": "play",
    }
    substitutions = {
        "LEGAL_ISO": "USD|EUR",  # legal ISO currency codes
        "LS": "\\$|\u20ac|\xe2\x82\xac|",  # Currency symbols - Euro(cp1252, utf-8)
        "NUM": r".,'\dKMB",
    }
    limits = {"NL": "nl", "PL": "pl", "": "fl", "FL": "fl", "Limit": "fl"}
    games = {  # base, category
        "Texas Hold'em": ("hold", "holdem"),
        "Texas Holdem": ("hold", "holdem"),
        "Hold'em": ("hold", "holdem"),
        "Holdem": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi": ("hold", "omahahi"),
        "Omaha Hi-Lo": ("hold", "omahahilo"),
        "7 Card Stud Hi-Lo": ("stud", "studhilo"),
        "7 Card Stud": ("stud", "studhi"),
        "Double Hold'em": ("hold", "2_holdem"),
        "Double Holdem": ("hold", "2_holdem"),
        "Short Deck": ("hold", "6_holdem"),
    }

    Lim_Blinds = {
        "0.04": ("0.01", "0.02"),
        "0.08": ("0.02", "0.04"),
        "0.10": ("0.02", "0.05"),
        "0.20": ("0.05", "0.10"),
        "0.30": ("0.07", "0.15"),
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
        "12.00": ("3.00", "6.00"),
        "12": ("3.00", "6.00"),
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
        "200.00": ("50.00", "100.00"),
        "200": ("50.00", "100.00"),
        "400.00": ("100.00", "200.00"),
        "400": ("100.00", "200.00"),
        "500.00": ("125.00", "250.00"),
        "500": ("125.00", "250.00"),
        "800.00": ("200.00", "400.00"),
        "800": ("200.00", "400.00"),
    }
    NLim_Blinds_20bb = {
        "0.80": ("0.01", "0.02"),
        "1.60": ("0.02", "0.04"),
        "4": ("0.05", "0.10"),
        "10": ("0.10", "0.25"),
        "20": ("0.25", "0.50"),
        "40": ("0.50", "1.00"),
        "240": ("3.00", "6.00"),
    }

    months = {
        "January": 1,
        "Jan": 1,
        "February": 2,
        "Feb": 2,
        "March": 3,
        "Mar": 3,
        "April": 4,
        "Apr": 4,
        "May": 5,
        "June": 6,
        "Jun": 6,
        "July": 7,
        "Jul": 7,
        "August": 8,
        "Aug": 8,
        "September": 9,
        "Sep": 9,
        "October": 10,
        "Oct": 10,
        "November": 11,
        "Nov": 11,
        "December": 12,
        "Dec": 12,
    }

    sites = {
        "Poker Stars": ("PokerStars", 2),
        "PokerMaster": ("PokerMaster", 25),
        "IPoker": ("iPoker", 14),
        "Party": ("PartyPoker", 9),
        "Pacific": ("PacificPoker", 10),
        "WPN": ("WinningPoker", 24),
        "PokerBros": ("PokerBros", 29),
    }

    # Static regexes
    re_GameInfo = re.compile(
        """
            \\*{{5}}\\sHand\\sHistory\\s(F|f)or\\sGame\\s(?P<HID>\\w+)\\s\\*{{5}}(\\s\\((?P<SITE>Poker\\sStars|PokerMaster|Party|PartyPoker|IPoker|Pacific|WPN|PokerBros)\\))?\\s+
            (.+?\\shas\\sleft\\sthe\\stable\\.\\s+)*
            (.+?\\sfinished\\sin\\s\\d+\\splace\\.\\s+)*
            ((?P<CURRENCY>[{LS}]))?\\s*
            (
            ([{LS}]?(?P<SB>[{NUM}]+)/[{LS}]?(?P<BB>[{NUM}]+)\\s*(?:{LEGAL_ISO})?\\s+(?P<FAST3>(fastforward|SPOTPOKER)\\s)?((?P<LIMIT3>NL|PL|FL|)\\s+)?)|
            ((?P<CASHBI>[{NUM}]+)\\s*(?:{LEGAL_ISO})?\\s*)(?P<FAST2>(fastforward|SPOTPOKER)\\s)?(?P<LIMIT2>(NL|PL|FL|))?\\s*
            )
            (Tourney\\s*)?
            (?P<GAME>(Texas\\sHold\'?em|Hold\'?em|Omaha\\sHi-Lo|Omaha(\\sHi)?|7\\sCard\\sStud\\sHi-Lo|7\\sCard\\sStud|Double\\sHold\'?em|Short\\sDeck))\\s*
            (Game\\sTable\\s*)?
            (
            (\\((?P<LIMIT>(NL|PL|FL|Limit|))\\)\\s*)?
            (\\((?P<SNG>SNG|STT|MTT)(\\sJackPot)?\\sTournament\\s\\#(?P<TOURNO>\\d+)\\)\\s*)?
            )?
            (?:\\s\\(Buyin\\s(?P<BUYIN>[{LS}][{NUM}]+)\\s\\+\\s(?P<FEE>[{LS}][{NUM}]+)\\))?
            \\s*-\\s*
            (?P<DATETIME>.+)
            """.format(**substitutions),
        re.VERBOSE | re.UNICODE,
    )

    re_HandInfo = re.compile(
        r"""
            Table\s(?P<TABLE>.+?)?\s+
            ((?: \#|\(|)(?P<TABLENO>\d+)\)?\s+)?
            (\(No\sDP\)\s)?
            \(\s?(?P<PLAY>Real|Play)\s+Money\s?\)\s+(--\s*)? # FIXME: check if play money is correct
            Seat\s+(?P<BUTTON>\d+)\sis\sthe\sbutton
            (\s+Total\s+number\s+of\s+players\s+\:\s+(?P<PLYRS>\d+)/?(?P<MAX>\d+)?)?
            """,
        re.VERBOSE | re.MULTILINE | re.DOTALL,
    )

    re_GameInfoTrny1 = re.compile(
        """
            \\*{{5}}\\sHand\\sHistory\\s(F|f)or\\sGame\\s(?P<HID>\\w+)\\s\\*{{5}}\\s+
            (?P<LIMIT>(NL|PL|FL|))\\s*
            (?P<GAME>(Texas\\sHold\'em|Hold\'?em|Omaha\\sHi-Lo|Omaha(\\sHi)?|7\\sCard\\sStud\\sHi-Lo|7\\sCard\\sStud|Double\\sHold\'em|Short\\sDeck))\\s+
            (?:(?P<BUYIN>[{LS}]?\\s?[{NUM}]+)\\s*(?P<BUYIN_CURRENCY>{LEGAL_ISO})?\\s*Buy-in\\s+)?
            (\\+\\s(?P<FEE>[{LS}]?\\s?[{NUM}]+)\\sEntry\\sFee\\s+)?
            Trny:\\s?(?P<TOURNO>\\d+)\\s+
            Level:\\s*(?P<LEVEL>\\d+)\\s+
            ((Blinds|Stakes)(?:-Antes)?)\\(
                (?P<SB>[{NUM} ]+)\\s*
                /(?P<BB>[{NUM} ]+)
                (?:\\s*-\\s*(?P<ANTE>[{NUM} ]+)\\$?)?
            \\)
            \\s*\\-\\s*
            (?P<DATETIME>.+)
            """.format(**substitutions),
        re.VERBOSE | re.UNICODE,
    )

    re_GameInfoTrny2 = re.compile(
        r"""
            \*{{5}}\sHand\sHistory\s(F|f)or\sGame\s(?P<HID>\w+)\s\*{{5}}\s+
            (?P<LIMIT>(NL|PL|FL|))\s*
            (?P<GAME>(Texas\sHold'em|Hold'em|Omaha\sHi-Lo|Omaha(\sHi)?|7\sCard\sStud\sHi-Lo|7\sCard\sStud|Double\sHold'em|Short\sDeck))\s+
            (?P<BUYIN_CURRENCY>[{LS}])?(?P<BUYIN>[{NUM}]+(\.[{NUM}]+)?)\s*(?P<BUYIN_ISO>{LEGAL_ISO})?\s*Buy-in\s*-\s*
            (?P<DATETIME>.+)
            """.format(**substitutions),
        re.VERBOSE | re.UNICODE,
    )

    re_GameInfoTrny3 = re.compile(
        """
            \\*{{5}}\\sHand\\sHistory\\s(F|f)or\\sGame\\s(?P<HID>\\w+)\\s\\*{{5}}\\s\\((?P<SITE>Poker\\sStars|PokerMaster|Party|IPoker|Pacific|WPN|PokerBros)\\)\\s+
            Tourney\\sHand\\s
            (?P<LIMIT>(NL|PL|FL|))\\s*
            (?P<GAME>(Texas\\sHold\'em|Hold\'?em|Omaha\\sHi-Lo|Omaha(\\sHi)?|7\\sCard\\sStud\\sHi-Lo|7\\sCard\\sStud|Double\\sHold\'em|Short\\sDeck))\\s+
            \\s*\\-\\s*
            (?P<DATETIME>.+)
            """.format(),
        re.VERBOSE | re.UNICODE,
    )

    re_Blinds = re.compile(
        r"""
            ^((Blinds|Stakes)(?:-Antes)?)\(
                (?P<SB>[{NUM} ]+)\s*
                /(?P<BB>[{NUM} ]+)
                (?:\s*-\s*(?P<ANTE>[{NUM} ]+)\$?)?
            \)$""".format(**substitutions),
        re.VERBOSE | re.MULTILINE,
    )

    re_TourNoLevel = re.compile(
        r"""
            Trny:\s?(?P<TOURNO>\d+)\s+
            Level:\s*(?P<LEVEL>\d+)
        """,
        re.VERBOSE,
    )

    re_PlayerInfo = re.compile(
        r"""
          (S|s)eat\s?(?P<SEAT>\d+):\s
          (?P<PNAME>.*)\s
          \(\s*[{LS}]?(?P<CASH>[{NUM}]+)\s*(?:{LEGAL_ISO}|)\s*\)
          """.format(**substitutions),
        re.VERBOSE | re.UNICODE,
    )

    re_NewLevel = re.compile(
        r"Blinds(-Antes)?\((?P<SB>[{NUM} ]+)/(?P<BB>[{NUM} ]+)(?:\s*-\s*(?P<ANTE>[{NUM} ]+))?\)".format(**substitutions),
        re.VERBOSE | re.MULTILINE | re.DOTALL,
    )
    re_CountedSeats = re.compile(
        r"Total\s+number\s+of\s+players\s*:\s*(?P<COUNTED_SEATS>\d+)", re.MULTILINE,
    )
    re_identify = re.compile(r"\*{5}\sHand\sHistory\s[fF]or\sGame\s\d+\w+?\s")
    re_SplitHands = re.compile("Game\\s*\\#\\d+\\s*starts.\n\n+\\#Game\\s*No\\s*\\:\\s*\\d+\\s*")
    re_TailSplitHands = re.compile("(\x00+)")
    lineSplitter = "\n"
    re_Button = re.compile(r"Seat (?P<BUTTON>\d+) is the button", re.MULTILINE)
    re_Board = re.compile(r"\[(?P<CARDS>.+)\]")
    re_NoSmallBlind = re.compile(
        "^There is no Small Blind in this hand as the Big Blind "
        "of the previous hand left the table",
        re.MULTILINE,
    )
    re_20BBmin = re.compile(r"Table 20BB Min")
    re_Cancelled = re.compile(r"Table\sClosed\s?", re.MULTILINE)
    re_Disconnected = re.compile(
        r"Connection\sLost\sdue\sto\ssome\sreason\s?", re.MULTILINE,
    )
    re_GameStartLine = re.compile(r"Game\s\#\d+\sstarts", re.MULTILINE)
    re_emailedHand = re.compile(r"\*\*\sSummary\s\*\*")

    re_WinningRankOne = re.compile(
        r"^Congratulations to player (?P<PNAME>.+?) for winning tournament .*",
        re.MULTILINE,
    )

    re_WinningRankOther = re.compile(
        r"^Player\s+(?P<PNAME>.+?)\s+finished\s+in\s+(?P<RANK>\d+)\s+place\s+and\s+received\s+(?P<CURRENCY_SYMBOL>[€$])(?P<AMT>[,\.0-9]+)\s+(?P<CURRENCY_CODE>[A-Z]{3})\s*$",
        re.MULTILINE,
    )

    re_RankOther = re.compile(
        r"^Player\s+(?P<PNAME>.+?)\s+finished\s+in\s+(?P<RANK>\d+)\.?\s*$",
        re.MULTILINE,
    )

    def __init__(
        self,
        config,
        in_path="-",
        out_path="-",
        index=0,
        autostart=True,
        starsArchive=False,
        ftpArchive=False,
        sitename="PartyPoker",
    ) -> None:
        log.debug(
            f"Initializing PartyPoker parser in_path: {in_path}, out_path: {out_path}, index: {index}, sitename: {sitename}",
        )

        super().__init__(
            config,
            in_path,
            out_path,
            index,
            autostart,
            starsArchive,
            ftpArchive,
            sitename,
        )

        log.info("Initialized base parser")

        self.last_bet = {}
        self.player_bets = {}
        self.playerMap = {}  # Initialize playerMap here

        # Define and initialize regex patterns
        self.re_Action = re.compile(
            r"(?P<PNAME>.+?)\s(?P<ATYPE>bets|checks|raises|completes|bring-ins|calls|folds|is\sall-In|double\sbets)"
            r"(?:\s*[\[\(\)\]]?\s?(€|$)?(?P<BET>[.,\d]+)\s*(EUR|USD)?\s*[\]\)]?)?"
            r"(?:\sto\s[.,\d]+)?\.?\s*$",
            re.MULTILINE,
        )

        # Initialize database connection if needed
        if not hasattr(self, "db"):
            self.db = Database.Database(self.config)
            log.debug(f"Initialized database connection config: {self.config!s}")

        log.debug(
            f"Completed PartyPoker parser initialization sitename: {sitename}, has_db: {hasattr(self, 'db')}",
        )

    def allHandsAsList(self):
        log.info("Starting hands list retrieval")

        hands = HandHistoryConverter.allHandsAsList(self)

        if hands is None:
            log.warning("No hands found in history result: empty")
            return []

        filtered_hands = list(filter(lambda text: len(text.strip()), hands))

        log.debug(
            f"Retrieved and filtered hands total_hands: {len(hands)}, filtered_hands: {len(filtered_hands)}, empty_hands: {len(hands) - len(filtered_hands) if hands else 0}",
        )

        return filtered_hands

    def compilePlayerRegexs(self, hand) -> None:
        log.debug(f"Starting regex compilation for players hand_id: {hand.handid}")

        players = {player[1] for player in hand.players}
        log.debug(f"Players identified players: {list(players)}, count: {len(players)}")

        if not hasattr(self, "compiledPlayers") or not players <= self.compiledPlayers:
            log.debug(
                "Compiling new regex patterns reason: New players or no existing patterns",
            )

            self.compiledPlayers = players
            player_re = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"

            subst = {
                "PLYR": player_re,
                "CUR_SYM": self.sym.get(hand.gametype["currency"], ""),
                "CUR": hand.gametype["currency"],
                "BRAX": r"\[\(\)\]",
            }

            log.debug(
                f"Created substitution patterns currency: {hand.gametype['currency']}, currency_symbol: {subst['CUR_SYM']}",
            )

            # Compile regex
            patterns = {
                "re_PostSB": rf"{subst['PLYR']} posts small blind [\[\(\)\]]?{subst['CUR_SYM']}?(?P<SB>[.,0-9]+)\s*({subst['CUR']})?[\[\(\)\]]?\.?\s*$",
                "re_PostBB": rf"{subst['PLYR']} posts big blind [\[\(\)\]]?{subst['CUR_SYM']}?(?P<BB>[.,0-9]+)\s*({subst['CUR']})?[\[\(\)\]]?\.?\s*$",
                "re_PostDead": rf"{subst['PLYR']} posts big blind \+ dead [\[\(\)\]]?{subst['CUR_SYM']}?(?P<BBNDEAD>[.,0-9]+)\s*{subst['CUR_SYM']}?[\[\(\)\]]?\.?\s*$",
                "re_PostBUB": rf"{subst['PLYR']} posts button blind  ?[\[\(\)\]]?{subst['CUR_SYM']}?(?P<BUB>[.,0-9]+)\s*({subst['CUR']})?[\[\(\)\]]?\.?\s*$",
                "re_Antes": rf"{subst['PLYR']} posts ante(?: of)? [\[\(\)\]]?{subst['CUR_SYM']}?(?P<ANTE>[.,0-9]+)\s*({subst['CUR']})?[\[\(\)\]]?\.?\s*$",
                "re_Action": r"""(?P<PNAME>.+?)\s(?P<ATYPE>bets|checks|raises|completes|bring-ins|calls|folds|is\sall-In|double\sbets)(?:\s*[\[\(\)\]]?\s?(€|$)?(?P<BET>[.,\d]+)\s*(EUR|DOL)?\s*[\]\)]?)?(?:\sto\s[.,\d]+)?\.?\s*$""",
                "re_HeroCards": rf"Dealt to {subst['PLYR']} \[\s*(?P<NEWCARDS>.+)\s*\]",
                "re_ShownCards": rf"{subst['PLYR']} (?P<SHOWED>(?:doesn\'t )?shows?) \[ *(?P<CARDS>.+) *\](?P<COMBINATION>.+)\.",
                "re_CollectPot": rf"{subst['PLYR']}\s+wins\s+(Lo\s\()?{subst['CUR_SYM']}?(?P<POT>[.,\d]+)\s*({subst['CUR']})?\)?",
            }

            try:
                for name, pattern in patterns.items():
                    setattr(
                        self,
                        name,
                        re.compile(
                            pattern,
                            re.MULTILINE | (re.VERBOSE if name == "re_Action" else 0),
                        ),
                    )
                    log.debug(f"Compiled regex pattern pattern_name: {name}")

            except re.error as e:
                log.exception(
                    f"Failed to compile regex pattern pattern_name: {name}, error: {e!s}",
                )
                raise

            log.debug(
                f"Successfully compiled all regex patterns pattern_count: {len(patterns)}",
            )

        else:
            log.debug(
                f"Skipped compilation - patterns already exist compiled_players: {list(self.compiledPlayers)}",
            )

    def readSupportedGames(self):
        log.info("Getting supported games list")

        supported_games = [
            ["ring", "hold", "nl"],
            ["ring", "hold", "pl"],
            ["ring", "hold", "fl"],
            ["ring", "stud", "fl"],
            ["tour", "hold", "nl"],
            ["tour", "hold", "pl"],
            ["tour", "hold", "fl"],
            ["tour", "stud", "fl"],
        ]

        log.debug(
            f"Retrieved supported games ring_games: {len([g for g in supported_games if g[0] == 'ring'])}, "
            f"tournaments: {len([g for g in supported_games if g[0] == 'tour'])}, "
            f"hold_games: {len([g for g in supported_games if g[1] == 'hold'])}, "
            f"stud_games: {len([g for g in supported_games if g[1] == 'stud'])}, "
            f"total_games: {len(supported_games)}, "
            f"variants: {supported_games}",
        )

        return supported_games

    def readSTP(self, hand) -> None:
        log.debug(f"Starting STP read hand_id: {hand.handid}, status: not_implemented")
        log.warning(
            f"STP functionality not implemented hand_id: {hand.handid}, method: readSTP",
        )

    def determineGameType(self, handText):
        log.debug("Starting game type determination")

        # Clean input text
        handText = handText.replace("\x00", "")
        info, extra = {}, {}

        # Search game info using different patterns
        patterns = {
            "GameInfo": self.re_GameInfo,
            "GameInfoTrny1": self.re_GameInfoTrny1,
            "GameInfoTrny2": self.re_GameInfoTrny2,
            "GameInfoTrny3": self.re_GameInfoTrny3,
            "Disconnected": self.re_Disconnected,
            "Cancelled": self.re_Cancelled,
            "GameStartLine": self.re_GameStartLine,
        }

        m = None
        for pattern_name, pattern in patterns.items():
            m = pattern.search(handText)
            log.debug(f"Searching pattern pattern: {pattern_name}, found: {bool(m)}")

            if m:
                if pattern_name == "GameInfoTrny2":
                    m2 = self.re_TourNoLevel.search(handText)
                    m3 = self.re_Blinds.search(handText)
                    if m2 and m3:
                        extra.update(m2.groupdict())
                        extra.update(m3.groupdict())
                        log.debug("Found additional tournament info")
                    else:
                        m = None
                break

            if pattern_name == "Disconnected" and m:
                log.warning(f"Player disconnected partial_hand: {True}")
                msg = "Partial hand history: Player Disconnected"
                raise FpdbHandPartial(msg)

            if pattern_name == "Cancelled" and m:
                log.warning(f"Table closed partial_hand: {True}")
                msg = "Partial hand history: Table Closed"
                raise FpdbHandPartial(msg)

            if pattern_name == "GameStartLine" and m and len(handText) < 50:
                log.warning(f"Only game start line found partial_hand: {True}")
                msg = "Partial hand history: Game start line"
                raise FpdbHandPartial(msg)

        if not m:
            log.error(f"Could not determine game type hand_text: {handText[:200]}")
            msg = "Hand type determination failed"
            raise FpdbParseError(msg)

        # Process match groups
        mg = m.groupdict()
        mg.update(extra)

        log.debug(f"Extracted hand info groups: {mg}")

        # Set site info if available
        if mg.get("SITE"):
            self.sitename = self.sites.get(mg["SITE"], (self.sitename,))[0]
            self.siteId = self.sites.get(mg["SITE"], (self.siteId,))[1]
            log.info(
                f"Site determined site_name: {self.sitename}, site_id: {self.siteId}",
            )

        # Set limit type
        for limit_key in ["LIMIT", "LIMIT2", "LIMIT3"]:
            if mg.get(limit_key):
                info["limitType"] = self.limits.get(mg[limit_key], "fl")
                log.debug(
                    f"Limit type set limit_type: {info['limitType']}, source: {limit_key}",
                )
                break
        else:
            info["limitType"] = "fl"
            log.debug("Default limit type set limit_type: fl")

        # Set fast mode
        info["fast"] = bool(mg.get("FAST2") or mg.get("FAST3"))
        log.debug(f"Fast mode setting fast: {info['fast']}")

        # Set game type
        if mg.get("GAME"):
            info["base"], info["category"] = self.games.get(
                mg["GAME"], ("hold", "holdem"),
            )
            log.debug(
                f"Game type determined base: {info['base']}, category: {info['category']}",
            )
        else:
            log.error("Game type not found")
            msg = "Game not identified"
            raise FpdbParseError(msg)

        # Process cash buyin
        if mg.get("CASHBI"):
            mg["CASHBI"] = self.clearMoneyString(mg["CASHBI"])
            m_20BBmin = self.re_20BBmin.search(handText)

            try:
                if m_20BBmin:
                    info["sb"], info["bb"] = self.NLim_Blinds_20bb.get(
                        mg["CASHBI"], ("0.01", "0.02"),
                    )
                    info["buyinType"] = "shallow"
                    log.debug(
                        f"Using 20BB min blinds small_blind: {info['sb']}, big_blind: {info['bb']}, buyin_type: shallow",
                    )
                else:
                    cashbi_decimal = Decimal(mg["CASHBI"])
                    if cashbi_decimal >= 10000:
                        nl_bb = str((cashbi_decimal / 100).quantize(Decimal("0.01")))
                        info["buyinType"] = "deep"
                    else:
                        nl_bb = str((cashbi_decimal / 50).quantize(Decimal("0.01")))
                        info["buyinType"] = "regular"

                    info["sb"], info["bb"] = self.Lim_Blinds.get(
                        nl_bb, ("0.01", "0.02"),
                    )
                    log.debug(
                        f"Blinds determined from cash buyin small_blind: {info['sb']}, big_blind: {info['bb']}, buyin_type: {info['buyinType']}",
                    )

            except KeyError as e:
                log.exception(
                    f"Error processing cash buyin cashbi: {mg['CASHBI']}, error: {e!s}, hand_text: {handText[:200]}",
                )
                raise FpdbParseError

        else:
            # Handle blinds for different game types
            if info.get("category") == "6_holdem":
                info["sb"] = "0"
                info["bb"] = self.clearMoneyString(mg.get("SB", "0.02"))

            else:
                m = self.re_NewLevel.search(handText)
                if m:
                    mg["SB"] = m.group("SB")
                    mg["BB"] = m.group("BB")

                info["sb"] = self.clearMoneyString(mg.get("SB", "0.01"))
                info["bb"] = self.clearMoneyString(mg.get("BB", "0.02"))

            info["buyinType"] = "regular"

            log.debug(
                f"Blinds set from game info small_blind: {info['sb']}, big_blind: {info['bb']}, buyin_type: {info['buyinType']}",
            )

        # Set currency
        info["currency"] = self.currencies.get(mg.get("CURRENCY"), "EUR")
        log.debug(f"Currency set currency: {info['currency']}")

        # Set mixed game type if present
        if mg.get("MIXED"):
            info["mix"] = self.mixes.get(mg["MIXED"], "none")
            log.debug(f"Mixed game type mix: {info['mix']}")

        # Determine if tournament or ring game
        if "TOURNO" in mg and mg["TOURNO"] is None:
            info["type"] = "ring"
        else:
            info["type"] = "tour"
            info["currency"] = "T$"

        log.debug(
            f"Game format determined type: {info['type']}, currency: {info['currency']}",
        )

        # Special handling for fixed limit games
        if info.get("limitType") == "fl" and info.get("bb"):
            if info["type"] == "ring":
                try:
                    info["sb"], info["bb"] = self.Lim_Blinds.get(
                        mg["BB"], ("0.01", "0.02"),
                    )
                    log.debug(
                        f"Fixed limit ring game blinds small_blind: {info['sb']}, big_blind: {info['bb']}",
                    )
                except KeyError:
                    log.exception(
                        f"Error setting fixed limit ring blinds BB: {mg['BB']}, hand_text: {handText[:200]}",
                    )
                    raise FpdbParseError
            else:
                info["sb"] = str(
                    (Decimal(mg.get("SB", "0")) / 2).quantize(Decimal("0.01")),
                )
                info["bb"] = str(Decimal(mg.get("SB", "0")).quantize(Decimal("0.01")))
                log.debug(
                    f"Fixed limit tournament blinds small_blind: {info['sb']}, big_blind: {info['bb']}",
                )

        log.debug(f"Game type determination complete game_info: {info}")
        return info

    def readHandInfo(self, hand) -> None:
        log.debug(
            f"Starting hand info reading hand_id: {getattr(hand, 'handid', None)}",
        )

        info, m2, extra = {}, None, {}
        type3 = False

        # Clean text
        hand.handText = hand.handText.replace("\x00", "")

        # Check if emailed hand
        hand.emailedHand = bool(self.re_emailedHand.search(hand.handText))
        log.debug(f"Hand type determined - emailed_hand: {hand.emailedHand}")

        # Get basic hand info
        m = self.re_HandInfo.search(hand.handText, re.DOTALL)

        # Get game specific info based on type
        if hand.gametype["type"] == "ring" or hand.emailedHand:
            m2 = self.re_GameInfo.search(hand.handText)
            log.debug(f"Ring/email game info search - found: {bool(m2)}")
        else:
            # Tournament hand - try different patterns
            patterns = [
                ("GameInfoTrny1", self.re_GameInfoTrny1),
                ("GameInfoTrny2", self.re_GameInfoTrny2),
                ("GameInfoTrny3", self.re_GameInfoTrny3),
            ]

            for name, pattern in patterns:
                m2 = pattern.search(hand.handText)
                log.debug(
                    f"Tournament pattern search - pattern: {name}, found: {bool(m2)}",
                )

                if m2:
                    if name == "GameInfoTrny2":
                        m3 = self.re_TourNoLevel.search(hand.handText)
                        m4 = self.re_Blinds.search(hand.handText)
                        if m3 and m4:
                            extra.update(m3.groupdict())
                            extra.update(m4.groupdict())
                            log.debug("Found additional tournament info")
                        else:
                            m2 = None
                            continue

                    if name == "GameInfoTrny3":
                        type3 = True
                    break

        # Handle partial hands
        if not m:
            if self.re_Disconnected.search(hand.handText):
                log.warning(f"Player disconnected - partial: {True}")
                msg = "Partial hand history: Player Disconnected"
                raise FpdbHandPartial(msg)

            if self.re_Cancelled.search(hand.handText):
                log.warning(f"Table closed - partial: {True}")
                msg = "Partial hand history: Table Closed"
                raise FpdbHandPartial(msg)

            match_start = self.re_GameStartLine.match(hand.handText)
            if match_start and len(hand.handText) < 50:
                log.warning(f"Only game start line - partial: {True}")
                msg = "Partial hand history: Game start line"
                raise FpdbHandPartial(msg)

            log.error(f"Missing basic hand info - hand_text: {hand.handText[:200]}")
            msg = "Missing infos"
            raise FpdbParseError(msg)

        if not m2:
            log.error(f"Missing game specific info - hand_text: {hand.handText[:200]}")
            msg = "Missing infos"
            raise FpdbParseError(msg)

        # Combine all info
        info.update(m.groupdict())
        info.update(m2.groupdict())
        info.update(extra)

        log.debug(f"Collected hand info - info: {info}")

        # Process each info field
        for key, value in info.items():
            if key == "DATETIME":
                self._processDateTime(hand, value)

            elif key == "HID":
                self._processHID(hand, value)

            elif key == "TABLE":
                self._processTable(hand, info)

            elif key == "BUTTON":
                hand.buttonpos = int(value)
                log.debug(f"Set button position - position: {hand.buttonpos}")

            elif key == "TOURNO":
                self._processTourNo(hand, info)

            elif key == "BUYIN":
                self._processBuyin(hand, info)

            elif key == "LEVEL":
                hand.level = value
                log.debug(f"Set tournament level - level: {value}")

            elif key == "PLAY" and value != "Real":
                hand.gametype["currency"] = "play"
                log.debug("Set play money currency")

            elif key == "MAX" and value is not None:
                hand.maxseats = int(value)
                log.debug(f"Set max seats - seats: {hand.maxseats}")

        if type3:
            self._processType3Info(hand, info)

        log.debug(
            f"Completed hand info processing hand_id: {hand.handid}, type: {hand.gametype['type']}",
        )

    def _processDateTime(self, hand, datetime_str) -> None:
        log.debug(f"Processing datetime raw: {datetime_str}")

        m = re.search(
            r"\w+?,?\s*?(?P<M>\w+)\s+(?P<D>\d+),?\s+(?P<H>\d+):(?P<MIN>\d+):(?P<S>\d+)\s+((?P<TZ>[A-Z]+)\s+)?(?P<Y>\d+)",
            datetime_str,
            re.UNICODE,
        )

        if not m:
            log.error(f"Failed to parse datetime datetime: {datetime_str}")
            msg = f"Cannot parse date: {datetime_str}"
            raise FpdbParseError(msg)

        timezone = m.group("TZ") if m.group("TZ") else "ET"
        month = self.months.get(m.group("M"))

        if not month:
            log.error(f"Unknown month month: {m.group('M')}")
            msg = f"Unknown month: {m.group('M')}"
            raise FpdbParseError(msg)

        datetime_str = f"{m.group('Y')}/{month}/{m.group('D')} {m.group('H')}:{m.group('MIN')}:{m.group('S')}"

        try:
            hand.startTime = datetime.datetime.strptime(
                datetime_str, "%Y/%m/%d %H:%M:%S",
            )
            hand.startTime = HandHistoryConverter.changeTimezone(
                hand.startTime, timezone, "UTC",
            )
            log.debug(
                f"Set start time time: {hand.startTime!s}, timezone: {timezone}",
            )
        except Exception as e:
            log.exception(f"Error parsing datetime error: {e!s}")
            msg = "Error parsing date"
            raise FpdbParseError(msg)

    def _processHID(self, hand, hid) -> None:
        log.debug(f"Processing hand ID raw_hid: {hid}")

        if str(hid) == "1111111111":
            hand.handid = str(int(time.time() * 1000))
            hand.roundPenny = True
            log.debug(f"Generated hand ID hand_id: {hand.handid}, round_penny: True")
        else:
            if re.search("[a-z]", hid):
                hand.handid = hid[:13]
                hand.roundPenny = True
            else:
                hand.handid = hid

            log.debug(
                f"Set hand ID hand_id: {hand.handid}, round_penny: {hand.roundPenny}",
            )

    def _processTable(self, hand, info) -> None:
        log.debug("Processing table info")

        if "TOURNO" in info and info["TOURNO"] is None:
            if info.get("TABLENO"):
                hand.tablename = f"{info['TABLE']} {info['TABLENO']}"
            else:
                hand.tablename = info["TABLE"]
        else:
            hand.tablename = info.get("TABLENO", "Unknown")

        log.debug(f"Set table name table: {hand.tablename}")

    def _processTourNo(self, hand, info) -> None:
        log.debug("Processing tournament number")

        hand.tourNo = info["TOURNO"]

        if hand.emailedHand:
            hand.buyin = 0
            hand.fee = 0
            hand.buyinCurrency = "NA"

        log.debug(
            f"Set tournament info tour_no: {hand.tourNo}, buyin: {hand.buyin if hasattr(hand, 'buyin') else None}",
        )

    def _processBuyin(self, hand, info) -> None:
        log.debug("Processing buyin info")

        if info.get("TABLE") and "Freeroll" in info.get("TABLE"):
            hand.buyin = 0
            hand.fee = 0
            hand.buyinCurrency = "FREE"
            log.debug("Set freeroll tournament")

        elif info["BUYIN"] is None:
            hand.buyin = 0
            hand.fee = 0
            hand.buyinCurrency = "NA"
            log.debug("Set free tournament")

        elif hand.tourNo is not None:
            self._processTournamentBuyin(hand, info)

        log.debug(
            f"Completed buyin processing buyin: {hand.buyin}, currency: {hand.buyinCurrency}, fee: {hand.fee}",
        )

    def _processTournamentBuyin(self, hand, info) -> None:
        hand.buyin = 0
        hand.fee = 0
        hand.buyinCurrency = "NA"

        if "$" in info["BUYIN"]:
            hand.buyinCurrency = "USD"
        elif "€" in info["BUYIN"]:
            hand.buyinCurrency = "EUR"
        else:
            log.error(
                f"Unknown currency hand_id: {hand.handid}, buyin: {info['BUYIN']}",
            )
            raise FpdbParseError

        buyin_str = self.clearMoneyString(info["BUYIN"].strip("$€"))
        hand.buyin = int(100 * Decimal(buyin_str))

        if "FEE" in info and info["FEE"] is not None:
            fee_str = self.clearMoneyString(info["FEE"].strip("$€"))
            hand.fee = int(100 * Decimal(fee_str))

        log.debug(
            f"Set tournament buyin details buyin: {hand.buyin}, currency: {hand.buyinCurrency}, fee: {hand.fee}",
        )

    def _processType3Info(self, hand, info) -> None:
        log.debug("Processing type 3 tournament info")

        hand.tourNo = info.get("TABLE", "Unknown")
        hand.buyin = 0
        hand.fee = 0
        hand.buyinCurrency = "NA"

        log.debug(
            f"Set type 3 tournament details tour_no: {hand.tourNo}, buyin: {hand.buyin}, currency: {hand.buyinCurrency}",
        )

    def readButton(self, hand) -> None:
        log.debug(f"Starting button position read hand_id: {hand.handid}")

        m = self.re_Button.search(hand.handText)

        if m:
            hand.buttonpos = int(m.group("BUTTON"))
            log.debug(
                f"Button position found hand_id: {hand.handid}, button_position: {hand.buttonpos}",
            )
        else:
            log.info(
                f"No button position found hand_id: {hand.handid}, status: missing",
            )
        log.debug(
            f"Completed button position read hand_id: {hand.handid}, has_button: {bool(m)}",
        )

    def readPlayerStacks(self, hand) -> None:
        log.debug(
            f"Starting player stacks read hand_id: {hand.handid}, game_type: {hand.gametype['type']}",
        )
        self.playerMap = {}  # Initialize playerMap

        seat_info_list = []
        placeholder_seats = []
        placeholder_detected = False
        hero_seat_info = None

        # Collect seat information and identify placeholders
        for match in self.re_PlayerInfo.finditer(hand.handText):
            pname = match.group("PNAME").strip()
            cash = self.clearMoneyString(match.group("CASH"))
            seat = int(match.group("SEAT"))

            if pname == hand.hero:
                hero_seat_info = (seat, pname, cash)
                self.playerMap[pname] = pname
            elif pname.startswith("Player"):
                placeholder_seats.append((seat, cash))
                placeholder_detected = True
            else:
                seat_info_list.append((seat, pname, cash))
                self.playerMap[pname] = pname

        if placeholder_detected:
            log.debug(
                "Placeholder names detected in seat list. Replacing with real names from actions.",
            )

            # Collect real player names from the actions
            real_player_names = []
            for action in self.re_Action.finditer(hand.handText):
                pname = action.group("PNAME")
                if pname != hand.hero and pname not in real_player_names:
                    real_player_names.append(pname)

            # Check if the number of real player names matches the number of placeholders
            if len(real_player_names) == len(placeholder_seats):
                # Assign real player names to placeholder seats in order
                for (seat, cash), pname in zip(placeholder_seats, real_player_names, strict=False):
                    hand.addPlayer(seat, pname, cash)
                    log.debug(
                        f"Assigned real name to seat player: {pname}, seat: {seat}, stack: {cash}",
                    )
                    self.playerMap[pname] = pname
            else:
                # If mismatch, assign seats arbitrarily
                log.warning(
                    "Number of real player names does not match number of placeholder seats. Assigning seats arbitrarily.",
                )
                for seat_info, pname in zip(placeholder_seats, real_player_names, strict=False):
                    seat, cash = seat_info
                    hand.addPlayer(seat, pname, cash)
                    log.debug(
                        f"Assigned real name to seat arbitrarily player: {pname}, seat: {seat}, stack: {cash}",
                    )
                    self.playerMap[pname] = pname

            # Add any remaining real player names without seats
            if len(real_player_names) > len(placeholder_seats):
                for pname in real_player_names[len(placeholder_seats) :]:
                    seat = self._findFirstEmptySeat(hand, 1)
                    hand.addPlayer(seat, pname, "0")
                    log.debug(
                        f"Added extra player without seat info player: {pname}, seat: {seat}, stack: Unknown",
                    )
                    self.playerMap[pname] = pname
        else:
            # No placeholders detected, process normally
            for seat, pname, cash in seat_info_list:
                hand.addPlayer(seat, pname, cash)
                log.debug(
                    f"Added player with stack player: {pname}, seat: {seat}, stack: {cash}",
                )

        # Add the hero to the player list
        if hero_seat_info:
            seat, pname, cash = hero_seat_info
            hand.addPlayer(seat, pname, cash)
            log.debug(f"Added hero player: {pname}, seat: {seat}, stack: {cash}")

        log.debug(f"Completed player stacks read total_players: {len(hand.players)}")

    def _processEmailedPlayerName(self, hand, match, pname) -> None:
        """Handle player names in emailed hands."""
        subst = {"PLYR": re.escape(match.group("PNAME")), "SPACENAME": r"\s(.+)? "}

        re_PlayerName = re.compile(
            rf"^{subst['PLYR']}(?P<PNAMEEXTRA>{subst['SPACENAME']})balance\s",
            re.MULTILINE | re.VERBOSE,
        )

        name_match = re_PlayerName.search(hand.handText)
        if name_match and len(name_match.group("PNAMEEXTRA")) > 1:
            full_name = match.group("PNAME") + name_match.group("PNAMEEXTRA")
            full_name = full_name.strip()
            self.playerMap[match.group("PNAME")] = full_name
            log.debug(
                f"Updated emailed hand player name original: {match.group('PNAME')}, full_name: {full_name}",
            )

    def _processRingGame(self, hand, maxKnownStack, zeroStackPlayers) -> None:
        """Handle ring game specific player processing."""
        log.debug("Processing ring game players")

        # Compile regex patterns
        re_JoiningPlayers = re.compile(r"(?P<PLAYERNAME>.+?) has joined the table")
        re_BBPostingPlayers = re.compile(
            r"(?P<PLAYERNAME>.+?) posts big blind", re.MULTILINE,
        )
        re_LeavingPlayers = re.compile(r"(?P<PLAYERNAME>.+?) has left the table")

        # Find player movements
        joining_players = re_JoiningPlayers.findall(hand.handText)
        leaving_players = re_LeavingPlayers.findall(hand.handText)
        bb_posting_players = re_BBPostingPlayers.findall(hand.handText)

        log.debug(
            f"Found player movements joining: {joining_players}, leaving: {leaving_players}, posting_bb: {bb_posting_players}",
        )

        # Process zero stack players
        self._processZeroStackPlayers(
            hand, zeroStackPlayers, joining_players, leaving_players, maxKnownStack,
        )

        # Get current seated players
        seated_players = [player[1] for player in hand.players]
        log.debug(
            f"Current seated players: players: {seated_players}, count: {len(seated_players)}",
        )

        # Handle unseated active players
        unseated_active = list(set(bb_posting_players) - set(seated_players))
        if unseated_active:
            self._addUnseatedPlayers(hand, unseated_active, maxKnownStack)

    def _findFirstEmptySeat(self, hand, startSeat):
        """Find first available seat number."""
        log.debug(f"Searching for empty seat start: {startSeat}")

        occupied_seats = [player[0] for player in hand.players]
        seat = startSeat

        while seat in occupied_seats:
            seat += 1
            if seat > hand.maxseats:
                seat = 1
            if seat > 10:
                break

        log.debug(f"Found empty seat seat: {seat}")
        return seat

    def _processZeroStackPlayers(
        self, hand, zero_stack_players, joining, leaving, max_stack,
    ) -> None:
        """Process players with zero stacks."""
        log.debug(f"Processing zero stack players count: {len(zero_stack_players)}")

        for seat, pname, stack in zero_stack_players:
            if pname in joining:
                stack = str(max_stack)
                log.debug(
                    f"Adjusted joining player stack player: {pname}, new_stack: {stack}",
                )

            if pname not in leaving:
                hand.addPlayer(seat, pname, stack)
                log.debug(
                    f"Added zero stack player player: {pname}, seat: {seat}, stack: {stack}",
                )

    def _addUnseatedPlayers(self, hand, unseated_players, max_stack) -> None:
        """Add active players who are not yet seated."""
        log.debug(f"Adding unseated active players players: {unseated_players}")

        for player in unseated_players:
            new_seat = self._findFirstEmptySeat(hand, 1)
            hand.addPlayer(new_seat, player, str(max_stack))
            log.debug(
                f"Added unseated player player: {player}, seat: {new_seat}, stack: {max_stack}",
            )

    def markStreets(self, hand) -> None:
        log.debug(
            f"Starting streets marking hand_id: {hand.handid}, game_type: {hand.gametype['base']}",
        )

        street_patterns = {
            "hold": (
                r"\*{2} Dealing down cards \*{2}"
                r"(?P<PREFLOP>.+?)"
                r"(?:\*{2} Dealing Flop \*{2} (:?\s*)?(?P<FLOP>\[ \S\S, \S\S, \S\S \].+?))?"
                r"(?:\*{2} Dealing Turn \*{2} (:?\s*)?(?P<TURN>\[ \S\S \].+?))?"
                r"(?:\*{2} Dealing River \*{2} (:?\s*)?(?P<RIVER>\[ \S\S \].+?))?$"
            ),
            "stud": (
                r"(?P<ANTES>.+(?=\*\* Dealing \*\*)|.+)"
                r"(\*\* Dealing \*\*(?P<THIRD>.+(?=\*\* Dealing Fourth street \*\*)|.+))?"
                r"(\*\* Dealing Fourth street \*\*(?P<FOURTH>.+(?=\*\* Dealing Fifth street \*\*)|.+))?"
                r"(\*\* Dealing Fifth street \*\*(?P<FIFTH>.+(?=\*\* Dealing Sixth street \*\*)|.+))?"
                r"(\*\* Dealing Sixth street \*\*(?P<SIXTH>.+(?=\*\* Dealing River \*\*)|.+))?"
                r"(\*\* Dealing River \*\*(?P<SEVENTH>.+))?"
            ),
        }

        base = hand.gametype["base"]
        match = None

        if base in street_patterns:
            pattern = street_patterns[base]
            match = re.search(pattern, hand.handText, re.DOTALL)

            log.debug(
                f"Searched street pattern game_type: {base}, found: {bool(match)}",
            )
        else:
            log.warning(
                f"Unsupported game type for street marking game_type: {base}, hand_id: {hand.handid}",
            )
            return

        if match:
            # Add streets to hand
            hand.addStreets(match)

            streets = match.groupdict()
            log.debug(
                f"Marked street sections sections: {str({k: bool(v) for k, v in streets.items()})}",
            )

            # Log street actions
            if base == "hold":
                for street in ["PREFLOP", "FLOP", "TURN", "RIVER"]:
                    actions = match.group(street)
                    log.debug(
                        f"Street actions - street: {street}, has_actions: {bool(actions)}, actions: {actions if actions else None}",
                    )
        else:
            log.error(
                f"Street marking failed - hand_id: {hand.handid}, game_type: {base}, text_sample: {hand.handText[:100]}",
            )

        log.debug(
            f"Completed streets marking - hand_id: {hand.handid}, success: {bool(match)}",
        )

    def readCommunityCards(self, hand, street) -> None:
        log.debug(
            f"Entering readCommunityCards method - street: {street}, method: PartyPoker:readCommunityCards",
        )

        if street in ("FLOP", "TURN", "RIVER"):
            log.debug(
                f"Processing community cards - street: {street}, method: PartyPoker:readCommunityCards",
            )

            m = self.re_Board.search(hand.streets[street])
            if m:
                cards_str = m.group("CARDS")
                log.debug(
                    f"Found community cards - street: {street}, cards_string: {cards_str}, method: PartyPoker:readCommunityCards",
                )

                cards = self.renderCards(cards_str)
                log.debug(
                    f"Rendered community cards - street: {street}, cards: {cards}, method: PartyPoker:readCommunityCards",
                )

                hand.setCommunityCards(street, cards)
                log.info(
                    f"Set community cards - street: {street}, method: PartyPoker:readCommunityCards",
                )
            else:
                log.warning(
                    f"No community cards found - street: {street}, method: PartyPoker:readCommunityCards",
                )
        else:
            log.warning(
                f"Unknown or unsupported street - street: {street}, method: PartyPoker:readCommunityCards",
            )

        log.debug("Exiting readCommunityCards method PartyPoker:readCommunityCards")

    def readAntes(self, hand) -> None:
        log.debug("Entering readAntes method PartyPoker:readAntes")

        for m in self.re_Antes.finditer(hand.handText):
            player = m.group("PNAME")
            ante = self.clearMoneyString(m.group("ANTE"))
            hand.addAnte(player, ante)

            log.debug(
                f"Player posted ante - method: PartyPoker:readAntes, player: {player}, ante: {ante}",
            )

        log.info("Exiting readAntes method")

    def readBlinds(self, hand) -> None:
        log.debug("Entering readBlinds method PartyPoker:readBlinds")

        noSmallBlind = bool(self.re_NoSmallBlind.search(hand.handText))

        if (
            hand.gametype["type"] == "ring"
            or hand.gametype["sb"] is None
            or hand.gametype["bb"] is None
            or hand.roundPenny
        ):
            try:
                if not noSmallBlind:
                    for m in self.re_PostSB.finditer(hand.handText):
                        player = m.group("PNAME")
                        sb_amount = self.clearMoneyString(m.group("SB"))
                        hand.addBlind(player, "small blind", sb_amount)
                        if hand.gametype["sb"] is None:
                            hand.gametype["sb"] = sb_amount
                        log.debug(
                            f"Small blind posted - method: PartyPoker:readBlinds, player: {player}, amount: {sb_amount}",
                        )
            except Exception as e:
                hand.addBlind(None, None, None)
                log.exception(
                    f"No small blind found - method: PartyPoker:readBlinds - error: {e!s}",
                )

            for a in self.re_PostBB.finditer(hand.handText):
                player = a.group("PNAME")
                bb_amount = self.clearMoneyString(a.group("BB"))
                hand.addBlind(player, "big blind", bb_amount)

                if hand.gametype["bb"] is None:
                    hand.gametype["bb"] = bb_amount

                log.debug(
                    f"Big blind posted - method: PartyPoker:readBlinds, player: {player}, amount: {bb_amount}",
                )

            for a in self.re_PostBUB.finditer(hand.handText):
                player = a.group("PNAME")
                bub_amount = self.clearMoneyString(a.group("BUB"))
                hand.addBlind(player, "button blind", bub_amount)

                log.debug(
                    f"Button blind posted - method: PartyPoker:readBlinds, player: {player}, amount: {bub_amount}",
                )

            for a in self.re_PostDead.finditer(hand.handText):
                player = a.group("PNAME")
                amount = self.clearMoneyString(a.group("BBNDEAD"))
                hand.addBlind(player, "both", amount)

                log.debug(
                    f"Both blinds posted - method: PartyPoker:readBlinds, player: {player}, amount: {amount}",
                )

        else:
            if hand.buttonpos == 0:
                self.readButton(hand)

            playersMap = {
                f[0]: f[1:3]
                    for f in hand.players
                    if f[1] in hand.handText.split("Trny:")[-1]}
            maxSeat = max(playersMap)

            def findFirstNonEmptySeat(startSeat):
                while startSeat not in playersMap:
                    if startSeat >= maxSeat:
                        startSeat = 0
                    startSeat += 1
                return startSeat

            smartMin = lambda A, B: A if float(A) <= float(B) else B

            if noSmallBlind:
                hand.addBlind(None, None, None)
                smallBlindSeat = int(hand.buttonpos)
                log.warning("No small blind in this hand method PartyPoker:readBlinds")
            else:
                smallBlindSeat = (
                    int(hand.buttonpos)
                    if len(hand.players) == 2
                    else findFirstNonEmptySeat(int(hand.buttonpos) + 1)
                )
                blind = smartMin(hand.sb, playersMap[smallBlindSeat][1])
                player = playersMap[smallBlindSeat][0]
                hand.addBlind(player, "small blind", blind)

                log.debug(
                    f"Small blind posted - method: PartyPoker:readBlinds, player: {player}, amount: {blind}",
                )

            if hand.gametype["category"] == "6_holdem":
                bigBlindSeat = findFirstNonEmptySeat(smallBlindSeat + 1)
                blind = smartMin(hand.bb, playersMap[bigBlindSeat][1])
                player = playersMap[bigBlindSeat][0]
                hand.addBlind(player, "button blind", blind)

                log.debug(
                    f"Button blind posted - method: PartyPoker:readBlinds, player: {player}, amount: {blind}",
                )
            else:
                bigBlindSeat = findFirstNonEmptySeat(smallBlindSeat + 1)
                blind = smartMin(hand.bb, playersMap[bigBlindSeat][1])
                player = playersMap[bigBlindSeat][0]
                hand.addBlind(player, "big blind", blind)

                log.debug(
                    f"Big blind posted - method: PartyPoker:readBlinds, player: {player}, amount: {blind}",
                )

        log.info("Exiting readBlinds method")

    def readBringIn(self, hand) -> None:
        log.info("Entering readBringIn method")
        log.warning("Method not implemented")

    def readHoleCards(self, hand) -> None:
        log.info("Entering readHoleCards method")

        # Read hero's cards
        for street in ("PREFLOP",):
            if street in hand.streets:
                log.debug(
                    f"Reading hero hole cards - method: PartyPoker:readHoleCards, street: {street}",
                )

                for found in self.re_HeroCards.finditer(hand.streets[street]):
                    hand.hero = found.group("PNAME")
                    newcards = self.renderCards(found.group("NEWCARDS"))
                    hand.addHoleCards(
                        street,
                        hand.hero,
                        closed=newcards,
                        shown=False,
                        mucked=False,
                        dealt=True,
                    )

                    log.debug(
                        f"Found hero hole cards - method: PartyPoker:readHoleCards, player: {hand.hero}, cards: {newcards}",
                    )

        # Read other player's cards
        for street, text in hand.streets.items():
            if not text or street in ("PREFLOP", "DEAL"):
                continue

            log.debug(
                f"Reading other players hole cards - method: PartyPoker:readHoleCards, street: {street}",
            )

            for found in self.re_HeroCards.finditer(text):
                player = found.group("PNAME")
                newcards = self.renderCards(found.group("NEWCARDS"))
                hand.addHoleCards(
                    street,
                    player,
                    open=newcards,
                    closed=[],
                    shown=False,
                    mucked=False,
                    dealt=False,
                )

                log.debug(
                    f"Found player hole cards - method: PartyPoker:readHoleCards, player: {player}, street: {street}, cards: {newcards}",
                )

        log.info("Exiting readHoleCards method")

    def readAction(self, hand, street) -> None:
        log.debug(
            f"Entering readAction method - method: PartyPoker:readAction, street: {street}",
        )

        # Iterate over each action in the street
        m = self.re_Action.finditer(hand.streets[street])
        for action in m:
            playerName = action.group("PNAME")

            if ":" in playerName:
                continue  # Skip chat messages

            # Use the mapped player name if available
            if self.playerMap.get(playerName):
                playerName = self.playerMap.get(playerName)

            amount = (
                self.clearMoneyString(action.group("BET"))
                if action.group("BET")
                else None
            )
            actionType = action.group("ATYPE")

            # Handle different action types
            if actionType == "folds":
                hand.addFold(street, playerName)
                log.debug(
                    f"Player folded - method: PartyPoker:readAction, player: {playerName}",
                )

            elif actionType == "checks":
                hand.addCheck(street, playerName)
                log.debug(
                    f"Player checked - method: PartyPoker:readAction, player: {playerName}",
                )

            elif actionType == "calls":
                hand.addCall(street, playerName, amount)
                log.debug(
                    f"Player called - method: PartyPoker:readAction, player: {playerName}, amount: {amount}",
                )

            elif actionType == "raises":
                hand.addCallandRaise(street, playerName, amount)
                log.debug(
                    f"Player raised - method: PartyPoker:readAction, player: {playerName}, amount: {amount}",
                )

            elif actionType in ("bets", "double bets"):
                hand.addBet(street, playerName, amount)
                log.debug(
                    f"Player bet - method: PartyPoker:readAction, player: {playerName}, amount: {amount}",
                )

            elif actionType == "completes":
                hand.addComplete(street, playerName, amount)
                log.debug(
                    f"Player completed - method: PartyPoker:readAction, player: {playerName}, amount: {amount}",
                )

            elif actionType == "bring-ins":
                hand.addBringIn(playerName, amount)
                log.debug(
                    f"Player brought in - method: PartyPoker:readAction, player: {playerName}, amount: {amount}",
                )

            elif actionType == "is all-In":
                if amount:
                    hand.addAllIn(street, playerName, amount)
                    log.debug(
                        f"Player went all-in - method: PartyPoker:readAction, player: {playerName}, amount: {amount}",
                    )

            else:
                log.error(
                    f"Unimplemented action - method: PartyPoker:readAction, player: {playerName}, action_type: {actionType}, hand_id: {hand.handid}",
                )
                raise FpdbParseError

        log.debug(
            f"Exiting readAction method - method: PartyPoker:readAction, street: {street}",
        )

    def readShowdownActions(self, hand) -> None:
        log.debug("Entering readShowdownActions method")
        log.warning("Method not implemented")

    def readCollectPot(self, hand) -> None:
        log.info("Entering readCollectPot method")

        hand.setUncalledBets(True)

        for m in self.re_CollectPot.finditer(hand.handText):
            player = m.group("PNAME")
            pot = self.clearMoneyString(m.group("POT"))
            hand.addCollectPot(player=player, pot=pot)

            log.debug(
                f"Player collected pot method: PartyPoker:readCollectPot, player: {player}, amount: {pot}",
            )

        log.info("Exiting readCollectPot method")

    def readShownCards(self, hand) -> None:
        log.info("Entering readShownCards method")

        for m in self.re_ShownCards.finditer(hand.handText):
            if m.group("CARDS"):
                player = m.group("PNAME")
                cards = self.renderCards(m.group("CARDS"))
                mucked = "SHOWED" in m.groupdict() and m.group("SHOWED") != "shows"
                combination = m.group("COMBINATION")

                hand.addShownCards(
                    cards=cards,
                    player=player,
                    shown=True,
                    mucked=mucked,
                    string=combination,
                )

                log.debug(
                    f"Player showed cards method: PartyPoker:readShownCards, player: {player}, cards: {cards}, mucked: {mucked}, combination: {combination}",
                )

        log.info("Exiting readShownCards method")

    def readSummaryInfo(self, summaryInfoList) -> bool:
        log.debug("Entering readSummaryInfo method")
        log.warning("Method not implemented")
        return True

    def convert_to_decimal(self, string):
        dec = self.clearMoneyString(string)
        return Decimal(dec)

    def readTourneyResults(self, hand) -> None:
        log.info("Entering readTourneyResults method")

        # Initialize data structures
        hand.winnings = {}
        hand.ranks = {}
        hand.playersIn = []
        hand.isProgressive = False

        log.debug(
            "Initialized tournament data structures method: PartyPoker:readTourneyResults, is_progressive: False",
        )

        # Process tournament winner (rank 1)
        m = self.re_WinningRankOne.search(hand.handText)
        if m:
            winner = m.group("PNAME")

            if "AMT" in m.groupdict():
                amt_str = m.group("AMT").replace(",", ".")
                try:
                    amount = Decimal(amt_str)
                    hand.winnings[winner] = amount

                    log.debug(
                        f"Processed tournament winner method: PartyPoker:readTourneyResults, player: {winner}, amount: {amount}",
                    )
                except Exception as e:
                    hand.winnings[winner] = Decimal(0)
                    log.exception(
                        f"Error processing winner amount method: PartyPoker:readTourneyResults, player: {winner}, amount_string: {amt_str}, error: {e!s}",
                    )
            else:
                hand.winnings[winner] = Decimal(0)
                log.debug(
                    f"Winner found without amount method: PartyPoker:readTourneyResults, player: {winner}",
                )

            hand.ranks[winner] = 1
            hand.playersIn.append(winner)

        # Process other players with winnings
        for match in self.re_WinningRankOther.finditer(hand.handText):
            pname = match.group("PNAME")
            rank = int(match.group("RANK"))
            amt_str = match.group("AMT").replace(",", ".")

            try:
                amount = Decimal(amt_str)
            except Exception as e:
                amount = Decimal(0)
                log.exception(
                    f"Error processing player amount method: PartyPoker:readTourneyResults, player: {pname}, amount_string: {amt_str}, error: {e!s}",
                )

            # currency_symbol = match.group("CURRENCY_SYMBOL")
            currency_code = match.group("CURRENCY_CODE")

            hand.ranks[pname] = rank
            hand.winnings[pname] = amount
            hand.buyinCurrency = currency_code
            hand.currency = currency_code

            if pname not in hand.playersIn:
                hand.playersIn.append(pname)

            log.debug(
                f"Processed player with winnings method: PartyPoker:readTourneyResults, player: {pname}, rank: {rank}, amount: {amount}, currency: {currency_code}",
            )

        # Process other ranked players without winnings
        for match in self.re_RankOther.finditer(hand.handText):
            pname = match.group("PNAME")
            rank = int(match.group("RANK"))

            if pname not in hand.ranks:
                hand.ranks[pname] = rank
                log.debug(
                    f"Processed ranked player without winnings method: PartyPoker:readTourneyResults, player: {pname}, rank: {rank}",
                )

            if pname not in hand.playersIn:
                hand.playersIn.append(pname)

        # Set tournament attributes
        hand.entries = len(hand.playersIn)
        hand.prizepool = sum(hand.winnings.values())
        hand.isTournament = True
        hand.tourneyName = hand.tablename
        hand.isSng = True
        hand.isRebuy = False
        hand.isAddOn = False
        hand.isKO = False

        if not hasattr(hand, "endTime"):
            hand.endTime = hand.startTime

        # Create TourneySummary
        try:
            summary = TourneySummary(
                db=self.db,
                config=self.config,
                siteName=self.sitename,
                summaryText=hand.handText,
                builtFrom="HHC",
                header="",
            )

            # Set summary attributes
            summary.tourNo = hand.tourNo
            summary.buyin = hand.buyin
            summary.fee = hand.fee
            summary.buyinCurrency = hand.buyinCurrency
            summary.currency = hand.buyinCurrency
            summary.startTime = hand.startTime
            summary.endTime = hand.endTime
            summary.gametype = hand.gametype
            summary.maxseats = hand.maxseats
            summary.entries = hand.entries
            summary.speed = "Normal"
            summary.isSng = hand.isSng
            summary.isRebuy = hand.isRebuy
            summary.isAddOn = hand.isAddOn
            summary.isKO = hand.isKO

            # Add players to summary
            for pname, rank in hand.ranks.items():
                winnings = hand.winnings.get(pname, Decimal("0"))
                winningsCurrency = hand.buyinCurrency
                summary.addPlayer(
                    rank=rank,
                    name=pname,
                    winnings=int(winnings * 100),
                    winningsCurrency=winningsCurrency,
                    rebuyCount=0,
                    addOnCount=0,
                    koCount=0,
                )

                log.debug(
                    f"Added player to summary method: PartyPoker:readTourneyResults, player: {pname}, rank: {rank}, winnings: {winnings}, currency: {winningsCurrency}",
                )

            summary.insertOrUpdate()
            log.debug(
                f"Tournament summary saved method: PartyPoker:readTourneyResults, entries: {hand.entries}, prizepool: {hand.prizepool}",
            )

        except Exception as e:
            log.exception(
                f"Error processing tournament summary method: PartyPoker:readTourneyResults, error: {e!s}",
            )

        log.debug(
            f"Exiting readTourneyResults method - method: PartyPoker:readTourneyResults, total_players: {len(hand.ranks)}, total_winners: {len(hand.winnings)}",
        )

    @staticmethod
    def getTableTitleRe(type, table_name=None, tournament=None, table_number=None):
        log.debug(
            f"Processing table title parameters - type: {type}, table_name: {table_name}, tournament: {tournament}, table_number: {table_number}",
        )

        tournament = str(tournament) if tournament is not None else None
        table_number = str(table_number) if table_number is not None else None
        regex = rf"{re.escape(table_name)}" if table_name else ""

        if type == "tour":
            if table_name:
                TableName = table_name.split(" ")
                if len(TableName) > 1 and len(TableName[1]) > 6:
                    regex = rf"#?{re.escape(table_number)}"
                    log.info(f"Using table number regex pattern - regex: {regex}")
                else:
                    regex = rf"{re.escape(TableName[0])}.+Table\s#?{re.escape(table_number)}"
                    log.info(f"Using full table name regex pattern - regex: {regex}")
            else:
                # sng
                regex = rf"{re.escape(tournament)}.*{re.escape(table_number)}"
                log.info(f"Using tournament regex pattern - regex: {regex}")

        log.debug(f"Generated regex pattern - regex: {regex}")
        return regex

    @staticmethod
    def renderCards(string):
        log.debug(f"Processing cards string - input: {string}")

        cards = string.strip().split(" ")
        rendered_cards = list(filter(len, (x.strip(" ,") for x in cards)))

        log.debug(
            f"Cards rendering complete - input: {string}, output: {rendered_cards}",
        )

        return rendered_cards
