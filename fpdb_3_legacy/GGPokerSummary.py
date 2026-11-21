#!/usr/bin/env python
"""GGPoker tournament-summary parser (#868).

The client writes one summary per tournament, next to the hand histories:

    Tournament #249773363, Spin&Gold #7, Hold'em No Limit
    Buy-in: $0.25
    3 Players
    Total Prize Pool: $0.5
    Tournament started 2025/12/14 14:40:55
    2nd : Hero, $0
    You finished in 2nd place.

Only the hero's result is listed, under the name the hand histories give them
("Hero"). The buy-in is a single amount for a Spin&Gold, and the parts of the
entry otherwise ("$1.8+$0.2", or three parts for a bounty tournament); see
``split_buyin``. Times are the player's local wall clock, as in the hands.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from fpdb_3_legacy.GGPokerToFpdb import HAND_TIME_FORMAT, hand_time_to_utc
from fpdb_3_legacy.HandHistoryConverter import FpdbParseError
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.TourneySummary import TourneySummary

log = get_logger("ggpoker_summary_parser")

# Spin&Gold is GG's lottery sit-and-go: three players, and a prize pool drawn
# as a multiple of the buy-in before the first hand.
SPIN_PLAYERS = 3
RE_SPIN_NAME = re.compile(r"Spin\s*&\s*Gold", re.IGNORECASE)

_CURRENCY_SYMBOLS = "$€£¥₹"
# "$1,234.5": a sentence's closing full stop is not a decimal point.
_MONEY = rf"[{_CURRENCY_SYMBOLS}]?[0-9][,0-9]*(?:\.[0-9]+)?"


def _cents(amount: str) -> int:
    """Hundredths of a GG amount such as "$1,234.5"."""
    cleaned = amount.strip().strip(_CURRENCY_SYMBOLS).replace(",", "")
    try:
        return int(round(100 * Decimal(cleaned)))
    except InvalidOperation as exc:
        raise FpdbParseError(f"GGPokerSummary: unreadable amount {amount!r}") from exc


def split_buyin(parts: list[int]) -> tuple[int, int, int]:
    """The (buyin, fee, bounty) of a GG entry, from the amounts its "Buy-in:" line adds up.

    One amount is the whole entry, with no rake stated (Spin&Gold). Two are the
    prize-pool part and the rake. Three add a bounty; the rake is the smaller
    of the last two, whichever order they come in, since a bounty is always a
    large share of the entry and the rake a few percent of it. The bounty is
    counted in the buy-in, as the hand converter does.
    """
    if len(parts) == 1:
        return parts[0], 0, 0
    if len(parts) == 2:
        return parts[0], parts[1], 0
    prize, second, third = parts[:3]
    fee, bounty = min(second, third), max(second, third)
    return prize + bounty, fee, bounty


class GGPokerSummary(TourneySummary):
    """GGPoker tournament summary parser."""

    sitename = "GGPoker"
    siteId = 27
    filetype = "text"
    codepage: ClassVar = ("utf8", "cp1252")

    currencies: ClassVar = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "CNY", "₹": "INR"}

    # A summary opens on its tournament line, followed by the buy-in; a hand
    # history opens on "Poker Hand #", so the two never overlap.
    re_identify = re.compile(
        r"^\ufeff?Tournament\s\#\d+,\s.+\n\s*Buy-in:\s",
        re.MULTILINE,
    )
    # Split between summaries only: a file of one summary (what the client
    # writes) stays whole, so the importer's header/footer trimming never sees
    # a short leading or trailing piece it would mistake for one.
    re_split_tourneys = re.compile(r"\n\s*\n(?=\ufeff?Tournament\s\#\d+,\s)")

    re_tourney_info = re.compile(
        rf"""
          ^\ufeff?Tournament\s\#(?P<TOURNO>\d+),\s(?P<NAME_AND_GAME>[^\n]+?)\s*\n
          \s*Buy-in:\s(?P<BUYIN>{_MONEY}(?:\s*\+\s*{_MONEY})*|Freeroll)\s*\n
          \s*(?P<ENTRIES>[,0-9]+)\sPlayers?\s*\n
          (?:\s*Total\sPrize\sPool:\s(?P<PRIZEPOOL>{_MONEY})\s*\n)?
          \s*Tournament\sstarted\s(?P<DATETIME>\d{{4}}/\d{{2}}/\d{{2}}\s\d{{1,2}}:\d{{2}}:\d{{2}})
        """,
        re.VERBOSE | re.MULTILINE | re.IGNORECASE,
    )
    # "Hold'em No Limit", "Omaha Pot Limit", "PLO-5 Pot Limit", ... at the end of the line.
    re_game = re.compile(
        r",\s(?P<GAME>Hold'?em|Holdem|ShortDeck|Omaha(?:\sHi/Lo)?|Omaha5|Omaha6|PLO(?:-[56])?|PLO5|PLO6)"
        r"\s(?P<LIMIT>No\sLimit|Pot\sLimit|Fixed\sLimit|Limit)\s*$",
        re.IGNORECASE,
    )
    re_player = re.compile(
        rf"^\s*(?P<RANK>\d+)(?:st|nd|rd|th)\s:\s(?P<PNAME>.+?),\s(?P<WINNINGS>{_MONEY})\s*$",
        re.MULTILINE,
    )
    re_hero_finished = re.compile(
        r"^You\sfinished(?:\sthe\stournament)?\sin\s(?P<RANK>\d+)(?:st|nd|rd|th)\splace",
        re.MULTILINE,
    )
    re_hero_received = re.compile(rf"^You\sreceived\sa\stotal\sof\s(?P<AMOUNT>{_MONEY})", re.MULTILINE)

    games: ClassVar = {
        "holdem": ("hold", "holdem"),
        "hold'em": ("hold", "holdem"),
        "shortdeck": ("hold", "6_holdem"),
        "omaha": ("hold", "omahahi"),
        "omaha hi/lo": ("hold", "omahahilo"),
        "plo": ("hold", "omahahi"),
        "omaha5": ("hold", "5_omahahi"),
        "plo5": ("hold", "5_omahahi"),
        "plo-5": ("hold", "5_omahahi"),
        "omaha6": ("hold", "6_omahahi"),
        "plo6": ("hold", "6_omahahi"),
        "plo-6": ("hold", "6_omahahi"),
    }
    limits: ClassVar = {"no limit": "nl", "pot limit": "pl", "fixed limit": "fl", "limit": "fl"}

    def getSplitRe(self, head: str) -> re.Pattern[str]:
        """Regex the importer splits a file of several summaries with."""
        return self.re_split_tourneys

    def parseSummary(self) -> None:
        m = self.re_tourney_info.search(self.summaryText)
        if m is None:
            log.error("GGPokerSummary: could not parse tournament info: %r", self.summaryText[:200])
            raise FpdbParseError

        mg = m.groupdict()
        self.tourNo = mg["TOURNO"]
        self._read_name_and_game(mg["NAME_AND_GAME"])
        self._read_buyin(mg["BUYIN"])
        self.entries = int(mg["ENTRIES"].replace(",", ""))
        self.prizepool = _cents(mg["PRIZEPOOL"]) if mg["PRIZEPOOL"] else 0
        wall_clock = datetime.datetime.strptime(mg["DATETIME"], HAND_TIME_FORMAT)  # noqa: DTZ007 - zone resolved below
        self.startTime = hand_time_to_utc(wall_clock, None)

        if self.tourneyName and RE_SPIN_NAME.search(self.tourneyName):
            self.isSng = True
            self.isLottery = True
            self.maxseats = SPIN_PLAYERS
            if self.buyin > 0 and self.prizepool > 0:
                self.tourneyMultiplier = max(1, round(self.prizepool / (self.buyin + self.fee)))

        self._read_results()

    def _read_name_and_game(self, text: str) -> None:
        game = self.re_game.search(text)
        if game is None:
            # No game we know at the end of the line: keep the name whole and
            # let the hands say what was played.
            self.tourneyName = text.strip()
            self.gametype["base"], self.gametype["category"] = "hold", "holdem"
            self.gametype["limitType"] = "nl"
            return
        self.tourneyName = text[: game.start()].strip()
        self.gametype["base"], self.gametype["category"] = self.games.get(
            game.group("GAME").lower(), ("hold", "holdem")
        )
        self.gametype["limitType"] = self.limits.get(game.group("LIMIT").lower(), "nl")

    def _read_buyin(self, text: str) -> None:
        if text.lower() == "freeroll":
            self.buyin = self.fee = 0
            self.buyinCurrency = self.currency = "FREE"
            return
        symbol = next((c for c in text if c in self.currencies), "$")
        self.buyinCurrency = self.currency = self.currencies[symbol]
        parts = [_cents(part) for part in text.split("+")]
        self.buyin, self.fee, self.koBounty = split_buyin(parts)
        self.isKO = self.koBounty > 0

    def _read_results(self) -> None:
        listed = False
        for pm in self.re_player.finditer(self.summaryText):
            listed = True
            self.addPlayer(
                int(pm.group("RANK")),
                pm.group("PNAME").strip(),
                _cents(pm.group("WINNINGS")),
                self.currency,
                None,
                None,
                None,
            )
        if listed:
            return
        # No ranking line: the closing sentences still give the hero's result.
        finished = self.re_hero_finished.search(self.summaryText)
        if finished is None:
            return
        received = self.re_hero_received.search(self.summaryText)
        winnings = _cents(received.group("AMOUNT")) if received else 0
        self.addPlayer(int(finished.group("RANK")), "Hero", winnings, self.currency, None, None, None)
