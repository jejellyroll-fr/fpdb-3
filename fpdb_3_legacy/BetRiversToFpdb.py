#!/usr/bin/env python
# The camelCase converter API follows the *ToFpdb convention of every
# hand-history converter (base-class overrides cannot be renamed).
# pylint: disable=invalid-name
"""BetRivers Poker text hand-history converter -- file import only (#731).

BetRivers Poker (Rush Street Interactive, US states) writes PokerStars-like
cash-game hand histories::

    BetRivers Poker Hand #00000000: Hold'em No Limit ($0.10/$0.20) - 2026/02/11 19:46 EST
    Table ID '000000' 6-Max Seat #3 is the button
    Seat 6: Hero ($36.12 in chips) [hero]
    ...
    *** HOLE CARDS ***
    STP Added: $0.40
    ...
    *** SUMMARY ***
    Total pot $3.44 | Main pot $3.04 | STP $0.40 | Rake $0.16

BetRivers does not permit third-party HUDs, so the room is *import-only*
(:mod:`fpdb_3_legacy.disabled_sites`): its files are imported after the session
and nothing runs beside its client.

Where the format departs from PokerStars':

* the header time has **no seconds** and names its zone (``EST``/``EDT``). A
  time that cannot be read fails the hand rather than dating it 2000-01-01;
* ``Table ID '…'``, ``6-Max``, and a ``[hero]`` marker on the hero's seat line,
  which is how the hero is told apart: ``Dealt to`` lines also carry the cards
  of players who reach the showdown;
* **Splash the Pot** (``STP Added: $x``, from 2026-01-19) is money the room
  adds to the pot. Unlike CoinPoker's splash it is *in* the pot: the payouts
  share it, and the summary's ``Total pot`` counts it. It is recorded as room
  money in the pot (``Hand.addSTP``) and flagged in ``splashPot``, never as a
  bet, as rake or as anyone's winnings beyond what they collect. A "Big
  Splash" is dealt with no blinds and no action at all;
* payouts may come ``from side pot``;
* the showdown section is ``*** SHOWDOWN ***`` and a hand is described as
  ``shows [cards] for <hand>``.

Only cash games are read: no BetRivers tournament history has been seen.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from fpdb_3_legacy.loggingFpdb import get_logger

if TYPE_CHECKING:
    from fpdb_3_legacy.Hand import Hand, HoldemOmahaHand

log = get_logger("betrivers_parser")

_CUR = r"\$?"
#: The US Eastern zones a header names, as fixed offsets from UTC in hours.
_EASTERN_OFFSETS = {"EST": -5, "EDT": -4}
_AMT = r"[\d,]+(?:\.\d+)?"


def _money(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))


class BetRivers(HandHistoryConverter):
    """BetRivers Poker (site id 144): text hand-history import."""

    sitename = "BetRivers"
    siteId = 144
    filetype = "text"
    codepage = ("utf-8-sig", "utf8", "cp1252")

    #: BetRivers game label -> (base, category).
    games = {
        "Hold'em": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi/Lo": ("hold", "omahahilo"),
    }
    limits = {"No Limit": "nl", "Pot Limit": "pl", "Fixed Limit": "fl", "Limit": "fl"}

    # IdentifySite decodes as plain UTF-8, so a BOM may precede the first hand.
    re_identify = re.compile(r"^﻿?BetRivers Poker Hand #\d+:", re.MULTILINE)
    re_SplitHands = re.compile(r"(?:\s?\n){2,}")

    re_GameInfo = re.compile(
        r"^﻿?BetRivers Poker Hand #(?P<HID>\d+):[ \t]+"
        r"(?P<GAME>Hold'em|Omaha Hi/Lo|Omaha)[ \t]+(?P<LIMIT>No Limit|Pot Limit|Fixed Limit|Limit)[ \t]+"
        rf"\({_CUR}(?P<SB>{_AMT})/{_CUR}(?P<BB>{_AMT})(?:[ \t]+USD)?\)[ \t]+-[ \t]+"
        r"(?P<DATE>\d{4}/\d{2}/\d{2})[ \t]+(?P<TIME>\d{1,2}:\d{2}(?::\d{2})?)(?:[ \t]+(?P<TZ>[A-Z]{2,4}))?[ \t]*$",
        re.MULTILINE,
    )
    re_HandInfo = re.compile(
        r"^Table ID '(?P<TABLE>[^']+)' (?P<MAX>\d+)-Max Seat #(?P<BUTTON>\d+) is the button",
        re.MULTILINE,
    )
    re_PlayerInfo = re.compile(
        rf"^Seat (?P<SEAT>\d+): (?P<PNAME>.+?) \({_CUR}(?P<CASH>{_AMT}) in chips\)(?P<HERO> \[hero\])?[ \t]*$",
        re.MULTILINE,
    )
    re_STP = re.compile(rf"^STP Added: {_CUR}(?P<AMOUNT>{_AMT})", re.MULTILINE)
    re_StreetHeader = re.compile(r"^\*\*\* (?P<STREET>HOLE CARDS|FLOP|TURN|RIVER|SHOW ?DOWN|SUMMARY) \*\*\*")
    re_Board = re.compile(r"\[([^\]]+)\]")
    re_Rake = re.compile(rf"^Total pot {_CUR}{_AMT}.*\| Rake {_CUR}(?P<RAKE>{_AMT})", re.MULTILINE)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.compiledPlayers: set[str] = set()
        #: Patterns naming the hand's players, rebuilt when the players change.
        self._player_re: dict[str, re.Pattern[str]] = {}
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------
    # Regexes that name the hand's players
    # ------------------------------------------------------------------
    def compilePlayerRegexs(self, hand: Any) -> None:
        players = {player[1] for player in hand.players}
        if players == self.compiledPlayers:
            return
        self.compiledPlayers = players
        plyr = "(?P<PNAME>" + "|".join(map(re.escape, sorted(players, key=len, reverse=True))) + ")"
        lines = {
            "post_sb": rf"^{plyr}: posts small blind {_CUR}(?P<AMOUNT>{_AMT})",
            "post_bb": rf"^{plyr}: posts big blind {_CUR}(?P<AMOUNT>{_AMT})",
            "post_both": rf"^{plyr}: posts small & big blinds {_CUR}(?P<AMOUNT>{_AMT})",
            "ante": rf"^{plyr}: posts (?:the )?ante {_CUR}(?P<AMOUNT>{_AMT})",
            "hero_cards": rf"^Dealt to {plyr} \[(?P<CARDS>[^\]]+)\]",
            "action": rf"^{plyr}: (?P<ATYPE>folds|checks|calls|bets|raises)"
            rf"(?: {_CUR}(?P<BET>{_AMT}))?(?: to {_CUR}(?P<TO>{_AMT}))?(?: and is all-in)?\s*$",
            "uncalled": rf"^Uncalled bet \({_CUR}(?P<AMOUNT>{_AMT})\) returned to {plyr}\s*$",
            "shows": rf"^{plyr} shows \[(?P<CARDS>[^\]]+)\](?: for (?P<STRING>.+?))?\s*$",
            "collect": rf"^{plyr} collected {_CUR}(?P<POT>{_AMT}) from (?:main |side )?pot",
            "shown_cards": rf"^Seat \d+: {plyr} (?:\([a-z ]+\) )*(?P<SHOWED>showed|mucked) "
            rf"\[(?P<CARDS>[^\]]+)\](?: and (?:won {_CUR}{_AMT}|lost))?(?: with (?P<STRING>.+?))?\s*$",
        }
        self._player_re = {name: re.compile(pattern, re.MULTILINE) for name, pattern in lines.items()}

    # ------------------------------------------------------------------
    # Game type and hand header
    # ------------------------------------------------------------------
    def readSupportedGames(self) -> list[list[str]]:
        return [["ring", "hold", "nl"], ["ring", "hold", "pl"], ["ring", "hold", "fl"]]

    def determineGameType(self, handText: str) -> dict[str, Any]:
        m = self.re_GameInfo.search(handText)
        if m is None:
            log.error("BetRiversToFpdb.determineGameType: '%s'", handText[:200])
            raise FpdbParseError
        base, category = self.games[m.group("GAME")]
        return {
            "type": "ring",
            "base": base,
            "category": category,
            "limitType": self.limits[m.group("LIMIT")],
            "currency": "USD",
            "sb": str(_money(m.group("SB"))),
            "bb": str(_money(m.group("BB"))),
        }

    def readHandInfo(self, hand: Hand) -> None:
        game = self.re_GameInfo.search(hand.handText)
        table = self.re_HandInfo.search(hand.handText)
        if game is None or table is None:
            log.error("BetRiversToFpdb.readHandInfo: '%s'", hand.handText[:200])
            raise FpdbParseError
        # Kept as the text the room wrote, as every converter does; the import
        # stores it as siteHandNo.
        hand.handid = game.group("HID")  # type: ignore[assignment]
        hand.startTime = self._start_time(game.group("DATE"), game.group("TIME"), game.group("TZ"))
        hand.tablename = table.group("TABLE")
        hand.maxseats = int(table.group("MAX"))
        hand.gametype["maxSeats"] = hand.maxseats
        hand.buttonpos = int(table.group("BUTTON"))

    @staticmethod
    def _start_time(date: str, time: str, zone: str | None) -> datetime.datetime:
        """The hand's start in UTC, from a header time that may lack seconds.

        BetRivers writes US Eastern times and says which: ``EST`` is UTC-5 and
        ``EDT`` UTC-4, whatever the date. Reading them as "US/Eastern" instead
        misdated the hour clocks fall back through, which happens twice: a
        01:30 EDT hand would have been taken for 01:30 EST. Only a header with
        no zone, or another one, is left to the regional zone rules. A time that
        does not parse is an error: PokerStars' converter, fed these headers,
        silently dated the hand 2000-01-01.
        """
        layout = "%Y/%m/%d %H:%M:%S" if time.count(":") == 2 else "%Y/%m/%d %H:%M"
        try:
            start = datetime.datetime.strptime(f"{date} {time}", layout)  # noqa: DTZ007
        except ValueError as error:
            msg = f"Unreadable BetRivers hand time: {date} {time}"
            raise FpdbParseError(msg) from error
        if (hours := _EASTERN_OFFSETS.get(zone or "")) is not None:
            return (start - datetime.timedelta(hours=hours)).replace(tzinfo=datetime.UTC)
        return HandHistoryConverter.changeTimezone(start, zone or "ET", "UTC")

    def readButton(self, hand: Hand) -> None:
        if m := self.re_HandInfo.search(hand.handText):
            hand.buttonpos = int(m.group("BUTTON"))

    def readPlayerStacks(self, hand: Hand) -> None:
        if "*** SUMMARY ***" not in hand.handText:
            self.raise_summary_partial(hand, "*** SUMMARY ***")
        seats = hand.handText.split("*** HOLE CARDS ***", 1)[0]
        seen: set[str] = set()
        for m in self.re_PlayerInfo.finditer(seats):
            if m.group("PNAME") not in seen:
                seen.add(m.group("PNAME"))
                hand.addPlayer(int(m.group("SEAT")), m.group("PNAME"), m.group("CASH").replace(",", ""))
                if m.group("HERO"):
                    hand.hero = m.group("PNAME")
        if len(seen) < 2:
            msg = f"Less than 2 players in hand! {hand.handid}."
            raise FpdbHandPartial(msg)

    # ------------------------------------------------------------------
    # Streets
    # ------------------------------------------------------------------
    def markStreets(self, hand: Hand) -> None:
        streets: dict[str, Any] = {"PREFLOP": None, "FLOP": None, "TURN": None, "RIVER": None}
        current: str | None = None
        for line in hand.handText.splitlines():
            header = self.re_StreetHeader.match(line)
            if header is None:
                if current is not None:
                    streets[current] = (streets[current] or "") + line + "\n"
                continue
            street = header.group("STREET")
            if street == "HOLE CARDS":
                current = "PREFLOP"
                streets[current] = ""
            elif street in ("FLOP", "TURN", "RIVER"):
                current = street
                streets[street] = line + "\n"
            else:  # SHOWDOWN / SUMMARY: no more betting
                current = None
        if streets["PREFLOP"] is None:
            msg = f"Hand '{hand.handid}' has no HOLE CARDS section."
            raise FpdbHandPartial(msg)
        hand.streets.update(streets)

    def readCommunityCards(self, hand: Hand, street: str) -> None:
        header = (hand.streets.get(street) or "").split("\n", 1)[0]
        if boards := self.re_Board.findall(header):
            hand.setCommunityCards(street, boards[-1].split())

    # ------------------------------------------------------------------
    # Forced bets and room money
    # ------------------------------------------------------------------
    def readBlinds(self, hand: Hand) -> None:
        live_sb = True
        for m in self._player_re["post_sb"].finditer(hand.handText):
            hand.addBlind(m.group("PNAME"), "small blind" if live_sb else "secondsb", m.group("AMOUNT"))
            live_sb = False
        for m in self._player_re["post_bb"].finditer(hand.handText):
            hand.addBlind(m.group("PNAME"), "big blind", m.group("AMOUNT"))
        for m in self._player_re["post_both"].finditer(hand.handText):
            hand.addBlind(m.group("PNAME"), "both", m.group("AMOUNT"))

    def readAntes(self, hand: Hand) -> None:
        for m in self._player_re["ante"].finditer(hand.handText):
            hand.addAnte(m.group("PNAME"), m.group("AMOUNT"))

    def readSTP(self, hand: Hand) -> None:
        """Splash the Pot: room money in the pot, shared by its winners."""
        drops = [_money(m.group("AMOUNT")) for m in self.re_STP.finditer(hand.handText)]
        if not drops:
            return
        splash = sum(drops, Decimal(0))
        hand.addSTP(str(splash))
        hand.splashPot = int(splash * 100)

    def readBringIn(self, hand: Hand) -> None:
        """No bring-in in hold'em games."""

    # ------------------------------------------------------------------
    # Cards and actions
    # ------------------------------------------------------------------
    def readHoleCards(self, hand: Hand) -> None:
        """The hero's cards. The other ``Dealt to`` lines are left to the showdown."""
        if not hand.hero:
            return
        for m in self._player_re["hero_cards"].finditer(hand.streets.get("PREFLOP") or ""):
            if m.group("PNAME") == hand.hero:
                hand.addHoleCards(
                    "PREFLOP",
                    hand.hero,
                    closed=m.group("CARDS").split(),
                    shown=False,
                    mucked=False,
                    dealt=True,
                )
                return

    def readAction(self, hand: Hand, street: str) -> None:
        text = hand.streets.get(street) or ""
        for m in self._player_re["action"].finditer(text):
            player, atype, bet = m.group("PNAME"), m.group("ATYPE"), m.group("BET")
            if atype == "folds":
                hand.addFold(street, player)
            elif atype == "checks":
                hand.addCheck(street, player)
            elif atype == "calls":
                hand.addCall(street, player, bet)
            elif atype == "bets":
                hand.addBet(street, player, bet)
            elif atype == "raises":
                hand.addRaiseTo(street, player, m.group("TO") or bet)
        for m in self._player_re["uncalled"].finditer(text):
            hand.addUncalled(street, m.group("PNAME"), m.group("AMOUNT"))

    def readShowdownActions(self, hand: HoldemOmahaHand) -> None:
        for m in self._player_re["shows"].finditer(hand.handText):
            hand.addShownCards(m.group("CARDS").split(), m.group("PNAME"), string=m.group("STRING"))

    def readShownCards(self, hand: HoldemOmahaHand) -> None:
        summary = hand.handText.split("*** SUMMARY ***", 1)[-1]
        for m in self._player_re["shown_cards"].finditer(summary):
            shown = m.group("SHOWED") == "showed"
            hand.addShownCards(
                cards=m.group("CARDS").split(),
                player=m.group("PNAME"),
                shown=shown,
                mucked=not shown,
                string=m.group("STRING"),
            )

    # ------------------------------------------------------------------
    # Money out
    # ------------------------------------------------------------------
    def readCollectPot(self, hand: Hand) -> None:
        """Main- and side-pot payouts from the showdown; the rake from the summary."""
        played = hand.handText.split("*** SUMMARY ***", 1)[0]
        for m in self._player_re["collect"].finditer(played):
            hand.addCollectPot(player=m.group("PNAME"), pot=str(_money(m.group("POT"))))
        rake = self.re_Rake.search(hand.handText)
        hand.rake = _money(rake.group("RAKE")) if rake else Decimal(0)

    def readSummaryInfo(self, summaryInfoList: Any) -> bool:
        return True

    def readTourneyResults(self, hand: Hand) -> None:
        """Cash games only: no BetRivers tournament history has been seen."""

    def readOther(self, hand: Hand) -> None:
        """Nothing beyond the PokerStars-like fields."""
