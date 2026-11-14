#!/usr/bin/env python
"""CoinPoker text hand-history converter -- file import only (#732).

CoinPoker's client exports cash-game hand histories in a PokerStars-like text
format::

    CoinPoker Hand #91198200457: PLO 4 (₮0.01/₮0.02) 2026/07/17 22:15:58 CEST
    Table '201383' 6-max Seat #1 is the button
    Seat 3: Hero (₮2 in chips)
    ...

fpdb reads those files for post-session review only. The room is
*import-only* (:mod:`fpdb_3_legacy.disabled_sites`): no HUD, no auto-import
and no live capture is offered for it, whatever the configuration says.

The format departs from PokerStars in a handful of ways, each handled here:

* amounts carry ``₮`` (USDT). They are stored as ``USD`` -- the currency the
  former live-capture import used, so both sources share their game types;
* ``ALLIN x`` gives the chips *added*, not a total. Whether it is a bet, a
  raise or a call is read off what the player already has in on the street;
* ``RETURN x`` is the uncalled part of a bet going back to its owner;
* ``AUTOBB x`` is a live big blind posted out of position (a player joining),
  ``STRADDLE x`` a straddle; both are written among the preflop actions. The
  preflop raises of a player who posted ``AUTOBB`` leave that blind out of
  their "to" figure, so it is added back;
* an all-in EV cash-out (insurance) is never named, but shows as payouts that
  do not add up to the pot: see :meth:`CoinPoker._ev_cash_out`;
* ``SPLASH dropped x`` / ``MEGA SPLASH dropped x`` is promotional money the
  room adds. The summary's ``Total pot`` includes it, but ``collected`` lines
  do not: the room credits it to the pot winners beside the pot (a winner's
  next stack shows it). It is therefore kept out of the pot and the rake, and
  credited to the winners in ``splashWinnings``, in proportion to what they
  collected -- the same split the live-capture builder used;
* a ``Splash Fee`` is a fee on top of the rake;
* bomb pots (``PLO 4 BombPot (sb/bb/ante)``) deal straight to the flop after
  every player antes, usually on two boards; the antes are recorded in
  ``bombPot`` and nobody gets a VPIP chance (see ``derived_stats_preflop``);
* boards dealt twice -- run-it-twice (``FIRST TURN``/``SECOND TURN`` after a
  shared flop) and double boards (``FIRST FLOP``/``SECOND FLOP``) -- keep the
  betting and board one on the base streets and board two on
  ``FLOP2``/``TURN2``/``RIVER2``, the shape ``DerivedStats.getBoardsList``
  encodes into the ``Boards`` table.

Hand numbers are the ones the live capture stored, so a hand imported both ways
is caught by the ordinary ``(siteHandNo, siteId)`` duplicate check.
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

log = get_logger("coinpoker_parser")

#: Optional currency mark in front of an amount. ``₮`` is the one observed.
_CUR = r"(?:₮|\$|€)?"
#: An amount, thousands separators allowed.
_AMT = r"[\d,]+(?:\.\d+)?"

_BOARD_STREETS = ("FLOP", "TURN", "RIVER")


def _money(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))


class CoinPoker(HandHistoryConverter):
    """CoinPoker (site id 140): text hand-history import."""

    sitename = "CoinPoker"
    siteId = 140
    filetype = "text"
    codepage = ("utf-8-sig", "utf8", "cp1252")

    #: CoinPoker game label -> (base, category, limit type).
    games = {
        "NLH": ("hold", "holdem", "nl"),
        "PLO": ("hold", "omahahi", "pl"),
        "PLO 4": ("hold", "omahahi", "pl"),
        "PLO 5": ("hold", "5_omahahi", "pl"),
        "PLO 6": ("hold", "6_omahahi", "pl"),
    }

    re_identify = re.compile(r"^CoinPoker Hand #\d+:", re.MULTILINE)
    re_SplitHands = re.compile(r"(?:\s?\n){2,}")

    re_GameInfo = re.compile(
        rf"^CoinPoker Hand #(?P<HID>\d+):\s+(?P<GAME>[A-Za-z]+(?: \d)?)(?P<BOMB> BombPot)?\s+"
        rf"\({_CUR}(?P<SB>{_AMT})/{_CUR}(?P<BB>{_AMT})(?:/{_CUR}(?P<BOMBANTE>{_AMT}))?\)\s+"
        r"(?P<DATETIME>\d{4}/\d{2}/\d{2} \d{1,2}:\d{2}:\d{2})(?:\s+(?P<TZ>[A-Z]+|[+-]\d{2}(?::?\d{2})?))?",
        re.MULTILINE,
    )
    re_HandInfo = re.compile(
        r"^Table '(?P<TABLE>[^']+)' (?P<MAX>\d+)-max Seat #(?P<BUTTON>\d+) is the button",
        re.MULTILINE,
    )
    re_PlayerInfo = re.compile(
        rf"^Seat (?P<SEAT>\d+): (?P<PNAME>.+?) \({_CUR}(?P<CASH>{_AMT}) in chips\)",
        re.MULTILINE,
    )
    re_Splash = re.compile(rf"^(?P<MEGA>MEGA )?SPLASH dropped {_CUR}(?P<AMOUNT>{_AMT})", re.MULTILINE)
    re_StreetHeader = re.compile(
        r"^\*\*\* (?:(?P<RUN>FIRST|SECOND) )?(?P<STREET>HOLE CARDS|FLOP|TURN|RIVER|SHOWDOWN|SUMMARY) \*\*\*"
    )
    re_Board = re.compile(r"\[([^\]]+)\]")
    re_TotalPot = re.compile(rf"^Total pot {_CUR}(?P<POT>{_AMT}) \| Rake {_CUR}(?P<RAKE>{_AMT})", re.MULTILINE)
    re_SplashFee = re.compile(rf"Splash Fee:? {_CUR}(?P<FEE>{_AMT})")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.compiledPlayers: set[str] = set()
        self._auto_bb: dict[str, Decimal] = {}
        super().__init__(*args, **kwargs)

    def processHand(self, handText: str) -> Hand:
        """Build the hand, then put back the rake the room reported.

        ``Hand.totalPot()`` re-derives a cash game's rake as pot minus pot
        payouts. That is the room's rake except when an all-in was insured:
        the cash-out fee the room kept would then be booked as rake.
        """
        hand = super().processHand(handText)
        rake = self._summary_rake(hand.handText)
        if hand.rake != rake:
            log.debug("CoinPoker hand %s: rake %s, not %s (cash-out fee)", hand.handid, rake, hand.rake)
            hand.rake = rake
        return hand

    # ------------------------------------------------------------------
    # Regexes that name the hand's players
    # ------------------------------------------------------------------
    def compilePlayerRegexs(self, hand: Any) -> None:
        players = {player[1] for player in hand.players}
        if players == self.compiledPlayers:
            return
        self.compiledPlayers = players
        plyr = "(?P<PNAME>" + "|".join(map(re.escape, sorted(players, key=len, reverse=True))) + ")"
        self.re_PostSB = re.compile(rf"^{plyr}: posts small blind {_CUR}(?P<AMOUNT>{_AMT})", re.MULTILINE)
        self.re_PostBB = re.compile(rf"^{plyr}: posts big blind {_CUR}(?P<AMOUNT>{_AMT})", re.MULTILINE)
        self.re_AutoBB = re.compile(rf"^{plyr}: (?:AUTOBB|posts auto big blind) {_CUR}(?P<AMOUNT>{_AMT})", re.MULTILINE)
        self.re_Straddle = re.compile(rf"^{plyr}: STRADDLE {_CUR}(?P<AMOUNT>{_AMT})", re.MULTILINE)
        self.re_Ante = re.compile(rf"^{plyr}: posts ante {_CUR}(?P<AMOUNT>{_AMT})", re.MULTILINE)
        self.re_HeroCards = re.compile(rf"^Dealt to {plyr} \[(?P<CARDS>[^\]]+)\]", re.MULTILINE)
        self.re_Action = re.compile(
            rf"^{plyr}: (?P<ATYPE>folds|checks|calls|bets|raises|ALLIN|RETURN)"
            rf"(?: {_CUR}(?P<BET>{_AMT}))?(?: to {_CUR}(?P<TO>{_AMT}))?\s*$",
            re.MULTILINE,
        )
        self.re_ShowdownAction = re.compile(rf"^{plyr}: shows \[(?P<CARDS>[^\]]+)\]", re.MULTILINE)
        self.re_CollectPot = re.compile(rf"^{plyr} collected {_CUR}(?P<POT>{_AMT}) from pot", re.MULTILINE)
        self.re_ShownCards = re.compile(
            rf"^Seat \d+: {plyr} (?P<SHOWED>showed|mucked) \[(?P<CARDS>[^\]]+)\](?P<RESULT>.*)$",
            re.MULTILINE,
        )

    # ------------------------------------------------------------------
    # Game type and hand header
    # ------------------------------------------------------------------
    def readSupportedGames(self) -> list[list[str]]:
        return [["ring", "hold", "nl"], ["ring", "hold", "pl"]]

    def determineGameType(self, handText: str) -> dict[str, Any]:
        m = self.re_GameInfo.search(handText)
        if m is None:
            log.error("CoinPokerToFpdb.determineGameType: '%s'", handText[:200])
            raise FpdbParseError
        game = self.games.get(m.group("GAME"))
        if game is None:
            log.error("CoinPoker: unsupported game %r in hand %s", m.group("GAME"), m.group("HID"))
            raise FpdbParseError
        base, category, limit = game
        return {
            "type": "ring",
            "base": base,
            "category": category,
            "limitType": limit,
            "currency": "USD",
            "sb": str(_money(m.group("SB"))),
            "bb": str(_money(m.group("BB"))),
        }

    def readHandInfo(self, hand: Hand) -> None:
        game = self.re_GameInfo.search(hand.handText)
        table = self.re_HandInfo.search(hand.handText)
        if game is None or table is None:
            log.error("CoinPokerToFpdb.readHandInfo: '%s'", hand.handText[:200])
            raise FpdbParseError
        # Kept as the text the room wrote, as every converter does; the import
        # stores it as siteHandNo.
        hand.handid = game.group("HID")  # type: ignore[assignment]
        start = datetime.datetime.strptime(game.group("DATETIME"), "%Y/%m/%d %H:%M:%S")  # noqa: DTZ007
        hand.startTime = self._to_utc(start, game.group("TZ"))
        hand.tablename = table.group("TABLE")
        hand.maxseats = int(table.group("MAX"))
        hand.gametype["maxSeats"] = hand.maxseats
        hand.buttonpos = int(table.group("BUTTON"))

    @staticmethod
    def _to_utc(start: datetime.datetime, zone: str | None) -> datetime.datetime:
        """The hand's start in UTC. The client writes its own zone: "CEST", "EDT", "-04"..."""
        offset = re.fullmatch(r"([+-])(\d{2}):?(\d{2})?", zone or "")
        if offset is None:
            # A zone name, or none at all: the exports seen without one were CET.
            return HandHistoryConverter.changeTimezone(start, zone or "CET", "UTC")
        sign = -1 if offset.group(1) == "-" else 1
        delta = datetime.timedelta(hours=int(offset.group(2)), minutes=int(offset.group(3) or 0))
        return (start - sign * delta).replace(tzinfo=datetime.UTC)

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
        if len(seen) < 2:
            msg = f"Less than 2 players in hand! {hand.handid}."
            raise FpdbHandPartial(msg)

    # ------------------------------------------------------------------
    # Streets
    # ------------------------------------------------------------------
    def markStreets(self, hand: Hand) -> None:
        """Cut the hand into streets, folding a second board onto the first.

        A street's betting is written after its *last* board header (both
        flops of a double board, then the betting), so the lines following a
        ``SECOND`` header go to the base street; the second board keeps only
        its header, which is where its cards are read from.
        """
        streets: dict[str, Any] = {"PREFLOP": None, "FLOP": None, "TURN": None, "RIVER": None}
        current: str | None = None
        second_board = False
        for line in hand.handText.splitlines():
            header = self.re_StreetHeader.match(line)
            if header is None:
                if current is not None:
                    streets[current] = (streets[current] or "") + line + "\n"
                continue
            street, run = header.group("STREET"), header.group("RUN")
            if street == "HOLE CARDS":
                current = "PREFLOP"
                streets[current] = ""
            elif street in _BOARD_STREETS:
                if run == "SECOND":
                    second_board = True
                    streets[f"{street}2"] = line + "\n"
                    streets[street] = streets.get(street) or ""
                else:
                    streets[street] = line + "\n" + (streets.get(street) or "")
                current = street
            else:  # SHOWDOWN / SUMMARY: no more betting
                current = None
        if streets["PREFLOP"] is None:
            msg = f"Hand '{hand.handid}' has no HOLE CARDS section."
            raise FpdbHandPartial(msg)
        hand.streets.update(streets)
        if second_board:
            hand.runItTimes = 2

    def readCommunityCards(self, hand: Hand, street: str) -> None:
        text = hand.streets.get(street) or ""
        for line in text.splitlines():
            if self.re_StreetHeader.match(line):
                boards = self.re_Board.findall(line)
                if boards:
                    hand.setCommunityCards(street, boards[-1].split())
                return

    # ------------------------------------------------------------------
    # Forced bets
    # ------------------------------------------------------------------
    def readBlinds(self, hand: Hand) -> None:
        live_sb = True
        for m in self.re_PostSB.finditer(hand.handText):
            hand.addBlind(m.group("PNAME"), "small blind" if live_sb else "secondsb", m.group("AMOUNT"))
            live_sb = False
        for m in self.re_PostBB.finditer(hand.handText):
            hand.addBlind(m.group("PNAME"), "big blind", m.group("AMOUNT"))
        # A joining player's live big blind, written among the preflop actions.
        self._auto_bb = {}
        for m in self.re_AutoBB.finditer(hand.handText):
            hand.addBlind(m.group("PNAME"), "big blind", m.group("AMOUNT"))
            self._auto_bb[m.group("PNAME")] = _money(m.group("AMOUNT"))
        for m in self.re_Straddle.finditer(hand.handText):
            hand.addBlind(m.group("PNAME"), "straddle", m.group("AMOUNT"))

    def readAntes(self, hand: Hand) -> None:
        for m in self.re_Ante.finditer(hand.handText):
            hand.addAnte(m.group("PNAME"), m.group("AMOUNT"))

    def readSTP(self, hand: Hand) -> None:
        """Flag a bomb pot. Its antes are the players' own money, already in the pot."""
        game = self.re_GameInfo.search(hand.handText)
        if game is None or not game.group("BOMB"):
            return
        total = sum((_money(m.group("AMOUNT")) for m in self.re_Ante.finditer(hand.handText)), Decimal(0))
        hand.bombPot = int(total * 100)

    def readBringIn(self, hand: Hand) -> None:
        """No bring-in in hold'em games."""

    # ------------------------------------------------------------------
    # Cards and actions
    # ------------------------------------------------------------------
    def readHoleCards(self, hand: Hand) -> None:
        """The hero is the player dealt visible cards.

        A history pasted from a room's back office shows every player's cards;
        the hero is then the one named ``Hero`` when there is one, else the
        first, and the others' cards are left to the showdown.
        """
        dealt = list(self.re_HeroCards.finditer(hand.streets.get("PREFLOP") or ""))
        if not dealt:
            return
        hero = next((m for m in dealt if m.group("PNAME") == "Hero"), dealt[0])
        hand.hero = hero.group("PNAME")
        hand.addHoleCards(
            "PREFLOP",
            hand.hero,
            closed=hero.group("CARDS").split(),
            shown=False,
            mucked=False,
            dealt=True,
        )

    def readAction(self, hand: Hand, street: str) -> None:
        for m in self.re_Action.finditer(hand.streets.get(street) or ""):
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
                to = _money(m.group("TO") or bet)
                if street == "PREFLOP":
                    # A player who posted AUTOBB has every preflop raise written
                    # as if that blind were not in ("raises 0.03 to 0.05" for a
                    # player then in for 0.07: the next caller calls 0.07).
                    to += self._auto_bb.get(player, Decimal(0))
                hand.addRaiseTo(street, player, str(to))
            elif atype == "ALLIN" and bet is not None:
                self._add_all_in(hand, street, player, bet)
            elif atype == "RETURN" and bet is not None:
                hand.addUncalled(street, player, bet)

    @staticmethod
    def _add_all_in(hand: Hand, street: str, player: str, amount: str) -> None:
        """``ALLIN x`` adds x chips: a bet, a raise or a (possibly short) call.

        Which one is told by what the player already has in on the street
        against the bet to match.
        """
        added = _money(amount)
        committed = sum(hand.bets[street].get(player, []), Decimal(0))
        to_match = Decimal(hand.lastBet.get(street) or 0)
        if to_match == 0:
            hand.addBet(street, player, str(added))
        elif committed + added > to_match:
            hand.addRaiseTo(street, player, str(committed + added))
        else:
            hand.addCall(street, player, str(added))

    def readShowdownActions(self, hand: HoldemOmahaHand) -> None:
        for m in self.re_ShowdownAction.finditer(hand.handText):
            hand.addShownCards(m.group("CARDS").split(), m.group("PNAME"))

    def readShownCards(self, hand: HoldemOmahaHand) -> None:
        summary = hand.handText.split("*** SUMMARY ***", 1)[-1]
        for m in self.re_ShownCards.finditer(summary):
            shown = m.group("SHOWED") == "showed"
            # "won (x) with Straight, and lost with Two Pair": one result per board.
            strings = re.findall(r"with ([^,]+)", m.group("RESULT"))
            hand.addShownCards(
                cards=m.group("CARDS").split(),
                player=m.group("PNAME"),
                shown=shown,
                mucked=not shown,
                string="|".join(s.strip() for s in strings) or None,
            )

    # ------------------------------------------------------------------
    # Money out
    # ------------------------------------------------------------------
    def readCollectPot(self, hand: Hand) -> None:
        """Pot payouts from the showdown lines, one per board; rake from the summary.

        The summary's ``Total pot`` is not used as the pot: it includes the
        splash, which nobody bet. Hand.totalPot() rebuilds the pot from the
        bets, and the rake the room reports (plus any splash fee) closes it.
        """
        rake = self._summary_rake(hand.handText)
        hand.rake = rake

        played = hand.handText.split("*** SUMMARY ***", 1)[0]
        payouts = [(m.group("PNAME"), _money(m.group("POT"))) for m in self.re_CollectPot.finditer(played)]
        insured, fee = self._ev_cash_out(hand, payouts, rake)
        for player, amount in payouts:
            if player == insured:
                hand.addCashOutPot(player, str(amount))
            else:
                hand.addCollectPot(player=player, pot=str(amount))
        if insured is not None:
            hand.cashedOut = True
            hand.isCashOut = True
            if fee:
                hand.cashOutFees[insured] = fee

    def _summary_rake(self, hand_text: str) -> Decimal:
        """The summary's rake, plus any splash fee."""
        rake = Decimal(0)
        if m := self.re_TotalPot.search(hand_text):
            rake = _money(m.group("RAKE"))
        for fee in self.re_SplashFee.finditer(hand_text):
            rake += _money(fee.group("FEE"))
        return rake

    @staticmethod
    def _ev_cash_out(hand: Hand, payouts: list[tuple[str, Decimal]], rake: Decimal) -> tuple[str | None, Decimal]:
        """The player paid an all-in EV cash-out (insurance), and the fee it cost.

        The text never says who insured an all-in, but the payouts give it
        away when they do not add up to the bets less the rake:

        * **more** than the pot: an insured player who lost is still written
          as having "collected" -- what the room pays them on top of the pot.
          The excess is exactly that one player's collections;
        * **less** than the pot: an insured winner is paid their cash-out
          instead of the pot, and the room keeps the difference -- the fee
          they gave up. Attributed only when a single player collected.

        Both shapes were checked against the hero's stack at the next hand:
        the written payouts are what the players really received.
        """
        pot = sum(hand.pot.committed.values(), Decimal(0)) + sum(hand.pot.common.values(), Decimal(0))
        gap = sum((amount for _player, amount in payouts), Decimal(0)) - (pot - rake)
        if gap == 0 or not payouts:
            return None, Decimal(0)
        by_player: dict[str, Decimal] = {}
        for player, amount in payouts:
            by_player[player] = by_player.get(player, Decimal(0)) + amount
        if gap > 0:
            matches = [player for player, amount in by_player.items() if amount == gap]
            if len(matches) == 1:
                log.info("CoinPoker hand %s: %s was paid an EV cash-out of %s", hand.handid, matches[0], gap)
                return matches[0], Decimal(0)
        elif len(by_player) == 1:
            (player,) = by_player
            log.info("CoinPoker hand %s: %s cashed out, leaving %s to the room", hand.handid, player, -gap)
            return player, -gap
        log.warning(
            "CoinPoker hand %s: payouts differ from the pot by %s and name no single insured player",
            hand.handid,
            gap,
        )
        return None, Decimal(0)

    def readOther(self, hand: Hand) -> None:
        """Credit a splash drop to the pot winners, beside the pot."""
        drops = list(self.re_Splash.finditer(hand.handText))
        if not drops:
            return
        splash = sum((_money(m.group("AMOUNT")) for m in drops), Decimal(0))
        hand.splashPot = int(splash * 100)
        won = {
            name: amount - hand.cashOutAmounts.get(name, Decimal(0))
            for name, amount in hand.collectees.items()
            if amount - hand.cashOutAmounts.get(name, Decimal(0)) > 0
        }
        collected = sum(won.values(), Decimal(0))
        if collected <= 0:
            log.warning("CoinPoker hand %s: splash of %s with no pot winner", hand.handid, splash)
            return
        winners = sorted(won.items(), key=lambda item: item[1], reverse=True)
        shares = {name: (splash * amount / collected).quantize(Decimal("0.01")) for name, amount in winners}
        # Rounding leftovers go to the largest winner, so the shares add up.
        shares[winners[0][0]] += splash - sum(shares.values(), Decimal(0))
        hand.splashWinnings = {name: share for name, share in shares.items() if share}
        if any(m.group("MEGA") for m in drops):
            log.info("CoinPoker hand %s: mega splash of %s", hand.handid, splash)

    def readSummaryInfo(self, summaryInfoList: Any) -> bool:
        return True

    def readTourneyResults(self, hand: Hand) -> None:
        """Cash games only: CoinPoker's export carries no tournament hands."""

    # ------------------------------------------------------------------
    # Table detection (kept for the window-title lookups; no HUD is offered)
    # ------------------------------------------------------------------
    @staticmethod
    def getTableTitleRe(
        type: Any = None,
        table_name: Any = None,
        tournament: Any = None,
        table_number: Any = None,
        tourney_name: Any = None,
    ) -> str:
        """Return a search string for CoinPoker table windows.

        CoinPoker's window title contains the numeric table id (e.g.
        "PLO4 921140 - ..."). Tournament rows use FPDB's ``<tourNo> <tableNo>``
        storage format, so ``table_number`` is preferred when given.
        """
        return re.escape(str(table_number or table_name or tournament or "CoinPoker"))

    @staticmethod
    def getTableNoRe(tournament: Any = None) -> str:
        return r"\b(\d+)\b"
