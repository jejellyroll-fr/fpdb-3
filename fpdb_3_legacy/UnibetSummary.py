#!/usr/bin/env python
"""Unibet (2026 / Relax Gaming client) tournament-summary parser.

Sample summary:

    === TOURNAMENT SUMMARIES ===

    Unibet Tournament #85614762, No Limit Holdem
    Buy-In: €0.93 + €0.07
    3 players
    Total Prize Pool: €4.00
    Tournament started 2026/06/05 21:50:39 UTC
    1: Unibet_28204e083c0fb55a finished €4.00
    2: DrikC79 finished
    3: evymm finished
    You finished in 1st place.

The hero is listed by their bare account token ("Unibet_<id>"), which is the
same token appended to the hero name in the hand histories. It is replaced with
the configured screen name so the summary result links to the imported hands.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import ClassVar

from fpdb_3_legacy.HandHistoryConverter import FpdbParseError
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.TourneySummary import TourneySummary

log = get_logger("unibet_summary_parser")


class UnibetSummary(TourneySummary):
    """Unibet 2026 tournament summary parser."""

    sitename = "Unibet"
    siteId = 30
    filetype = "text"
    codepage: ClassVar = ("utf8", "cp1252", "ISO-8859-1")

    limits: ClassVar = {"No Limit": "nl", "Pot Limit": "pl", "Limit": "fl"}
    games: ClassVar = {  # base, category
        "Holdem": ("hold", "holdem"),
        "Hold'em": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi/Lo": ("hold", "omahahilo"),
    }

    currencies: ClassVar = {"€": "EUR", "$": "USD", "£": "GBP"}

    re_identify = re.compile(r"Unibet\sTournament\s\#\d+")
    re_split_tourneys = re.compile(r"Unibet\sTournament\s\#")
    # Bare hero token used as a player name in summaries.
    re_HeroToken = re.compile(r"^Unibet_[0-9a-fA-F]+$")

    # The importer splits the file on "Unibet Tournament #" (see getSplitRe), so
    # each summary text starts at the tournament number.
    re_tourney_info = re.compile(
        r"""
          (?:Unibet\sTournament\s\#)?(?P<TOURNO>[0-9]+),\s(?P<GAME>[^\n]+?)\s*\n
          Buy-In:\s(?P<CURRENCY>[€$£])(?P<BUYIN>[.0-9]+)\s\+\s[€$£](?P<FEE>[.0-9]+)\s*\n
          (?P<ENTRIES>[0-9]+)\splayers\s*\n
          Total\sPrize\sPool:\s[€$£](?P<PRIZEPOOL>[.0-9]+)\s*\n
          Tournament\sstarted\s(?P<DATETIME>[0-9]{4}/[0-9]{2}/[0-9]{2}\s[0-9]+:[0-9]+:[0-9]+)\sUTC
        """,
        re.VERBOSE | re.MULTILINE,
    )
    re_player = re.compile(
        r"^(?P<RANK>[0-9]+):\s(?P<PNAME>.+?)\sfinished(\s(?P<CURRENCY>[€$£])(?P<WINNINGS>[.0-9]+))?\s*$",
        re.MULTILINE,
    )
    re_hero_finished = re.compile(r"You\sfinished\sin\s(?P<RANK>[0-9]+)(?:st|nd|rd|th)\splace")

    def getSplitRe(self, head: str) -> re.Pattern[str]:
        """Regex used by the importer to split a file into individual summaries."""
        return self.re_split_tourneys

    def _heroName(self) -> str | None:
        """Configured screen name for the hero, used to de-tokenise the winner."""
        try:
            return self.config.get_site_parameters(self.siteName).get("screen_name") or None
        except (AttributeError, KeyError, TypeError):
            log.debug("Unable to resolve configured Unibet hero name", exc_info=True)
            return None

    def parseSummary(self) -> None:
        m = self.re_tourney_info.search(self.summaryText)
        if m is None:
            tmp = self.summaryText[:200]
            log.error(f"UnibetSummary: could not parse tournament info: '{tmp}'")
            raise FpdbParseError

        mg = m.groupdict()
        self.tourNo = mg["TOURNO"]

        game = mg["GAME"].strip()
        if game in self.games:
            self.gametype["base"], self.gametype["category"] = self.games[game]
        else:
            low = game.lower()
            self.gametype["base"] = "hold"
            self.gametype["category"] = "omahahi" if "omaha" in low else "holdem"
        self.gametype["limitType"] = "pl" if game.lower().startswith("pot limit") else "nl"

        self.buyin = int(round(100 * Decimal(mg["BUYIN"])))
        self.fee = int(round(100 * Decimal(mg["FEE"])))
        self.buyinCurrency = self.currencies.get(mg["CURRENCY"], "EUR")
        self.currency = self.buyinCurrency
        self.entries = int(mg["ENTRIES"])
        self.prizepool = int(round(100 * Decimal(mg["PRIZEPOOL"])))

        self.startTime = datetime.datetime.strptime(  # noqa: DTZ007
            mg["DATETIME"],
            "%Y/%m/%d %H:%M:%S",
        )

        hero_name = self._heroName()

        for pm in self.re_player.finditer(self.summaryText):
            pmg = pm.groupdict()
            rank = int(pmg["RANK"])
            name = pmg["PNAME"].strip()
            # The hero appears as a bare "Unibet_<id>" token; map it to the
            # configured screen name so it matches the hand-history hero.
            if hero_name and self.re_HeroToken.match(name):
                name = hero_name
            winnings = 0
            if pmg.get("WINNINGS"):
                winnings = int(round(100 * Decimal(pmg["WINNINGS"])))
            self.addPlayer(rank, name, winnings, self.currency, None, None, None)
