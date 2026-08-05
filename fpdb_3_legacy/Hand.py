#!/usr/bin/env python
from __future__ import annotations

# Copyright 2008-2011 Carl Gherardi
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# In the "official" distribution you can find the license in agpl-3.0.txt.
import datetime
import pprint
import sys
from decimal import Decimal, InvalidOperation
from typing import Any, TextIO

from fpdb_3_legacy import Card, Configuration, DerivedStats
from fpdb_3_legacy.autonotes_aof import is_aof_category
from fpdb_3_legacy.Exceptions import FpdbHandDuplicate, FpdbHandPartial, FpdbParseError
from fpdb_3_legacy.loggingFpdb import get_logger

# import L10n
# _ = L10n.get_translation()

Configuration.set_logfile("fpdb-log.txt")

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("hand")

HAND_DECIMAL_ERRORS = (InvalidOperation, TypeError, ValueError)


def canonical_datetime_utc(value):
    if not value:
        return ""
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            value = value.replace(tzinfo=datetime.UTC)
        else:
            value = value.astimezone(datetime.UTC)
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class Hand:
    allStreets: list[str]
    actionStreets: list[str]
    communityStreets: list[str]
    holeStreets: list[str]
    discardStreets: list[str]
    sb: Decimal
    bb: Decimal
    handid_selected: int

    UPS = {
        "a": "A",
        "t": "T",
        "j": "J",
        "q": "Q",
        "k": "K",
        "S": "s",
        "C": "c",
        "H": "h",
        "D": "d",
    }
    LCS = {"H": "h", "D": "d", "C": "c", "S": "s"}
    SYMBOL = {
        "USD": "$",
        "CAD": "C$",
        "EUR": "€",
        "GBP": "£",
        "SEK": "kr.",
        "RSD": "РСД",
        "mBTC": "ⓑ",
        "INR": "₹",
        "CNY": "¥",
        "T$": "",
        "play": "",
    }
    MS = {"horse": "HORSE", "8game": "8-Game", "hose": "HOSE", "ha": "HA"}
    ACTION = {
        "ante": 1,
        "small blind": 2,
        "secondsb": 3,
        "big blind": 4,
        "both": 5,
        "calls": 6,
        "raises": 7,
        "bets": 8,
        "stands pat": 9,
        "folds": 10,
        "checks": 11,
        "discards": 12,
        "bringin": 13,
        "completes": 14,
        "straddle": 15,
        "button blind": 16,
        "cashout": 17,
    }

    def __init__(self, config, sitename, gametype, handText, builtFrom="HHC") -> None:
        self.config = config
        self.saveActions = self.config.get_import_parameters().get("saveActions")
        self.callHud = self.config.get_import_parameters().get("callFpdbHud")
        self.cacheSessions = self.config.get_import_parameters().get("cacheSessions")
        self.publicDB = self.config.get_import_parameters().get("publicDB")
        self.sitename = sitename
        self.siteId = self.config.get_site_id(sitename)
        self.stats = DerivedStats.DerivedStats()
        self.gametype = gametype
        # Robust default settings for gametype keys
        self.gametype.setdefault("mix", "none")
        self.gametype.setdefault("ante", 0)
        self.gametype.setdefault("buyinType", "regular")
        self.gametype.setdefault("fast", False)
        self.gametype.setdefault("newToGame", False)
        self.gametype.setdefault("homeGame", False)
        self.gametype.setdefault("split", False)
        self.gametype.setdefault("currency", "USD")
        self.startTime: datetime.datetime | int = 0
        self.handText = handText
        self.handid = 0
        self.in_path: str | None = None
        self.cancelled = False
        self.dbid_hands = 0
        self.playerIds: dict[str, int] = {}
        self.dbid_hpid: Any = None
        self.dbid_gt = 0
        self.tablename = ""
        self.hero = ""
        self.maxseats: int | None = None
        self.counted_seats = 0
        self.buttonpos = 0
        self.runItTimes = 0
        self.uncalledbets = False
        self.checkForUncalled = False
        self.adjustCollected = False
        self.cashedOut = False
        self.cashOutFees: dict[str, Decimal] = {}  # Cash out fees per player
        self.cashOutAmounts: dict[str, Decimal] = {}  # Insurance amounts per player
        self.endTime: datetime.datetime | None = None
        self.pot = Pot()  # Initialize the Pot instance
        self.roundPenny = False

        # tourney stuff
        self.tourNo: Any = None
        self.tourneyId: Any = None
        self.tourneyName: str | None = None
        self.tourneyTypeId: Any = None
        self.buyin: Any = None
        self.buyinCurrency: str | None = None
        self.buyInChips: Any = None
        self.fee: Any = None  # the Database code is looking for this one .. ?
        self.level: Any = None
        self.mixed: str | None = None
        self.speed = "Normal"
        self.isSng = False
        self.isRebuy = False
        self.rebuyCost = 0
        self.isAddOn = False
        self.addOnCost = 0
        self.isKO = False
        self.koBounty = 0
        self.isProgressive = False
        self.isMatrix = False
        self.isShootout = False
        self.isFast = False
        self.stack = "Regular"
        self.isStep = False
        self.stepNo = 0
        self.isChance = False
        self.chanceCount = 0
        self.isMultiEntry = False
        self.isReEntry = False
        self.isNewToGame = False
        self.isHomeGame = False
        self.isSplit = False
        self.isFifty50 = False
        self.isTime = False
        self.timeAmt = 0
        self.isSatellite = False
        self.isDoubleOrNothing = False
        self.isCashOut = False
        self.isOnDemand = False
        self.isFlighted = False
        self.isGuarantee = False
        self.guaranteeAmt = 0
        self.added: Any = None
        self.addedCurrency: str | None = None
        self.isLottery = False
        self.tourneyMultiplier = 1
        self.entryId = 1

        self.newAttribute = None

        self.seating: list[Any] = []
        self.players: list[Any] = []
        # Cache used for checkPlayerExists.
        self.player_exists_cache: set[str] = set()
        self.posted: list[Any] = []
        self.tourneysPlayersIds: dict[str, int] = {}
        self.tourneyRanks: dict[str, int] = {}
        self.tourneyWinnings: dict[str, Any] = {}
        self.tourneyWinningsCurrency: dict[str, str] = {}

        # Collections indexed by street names
        self.bets: dict[str, dict[str, list[Any]]] = {}
        self.lastBet: dict[str, Any] = {}
        self.streets: dict[str, str] = {}
        self.actions: dict[str, list[Any]] = {}
        self.board: dict[str, list[str]] = {}
        self.holecards: dict[str, dict[str, Any]] = {}
        self.discards: dict[str, dict[str, Any]] = {}
        self.showdownStrings: dict[str, Any] = {}
        # Per-player winning 5-card hand, when the history prints it explicitly
        # (used by the replayer to highlight the cards forming the combination).
        self.winningHand: dict[str, Any] = {}
        for street in self.allStreets:
            self.streets[street] = ""  # portions of the handText, filled by markStreets()
            self.actions[street] = []
        for street in self.actionStreets:
            self.bets[street] = {}
            self.lastBet[street] = 0
            self.board[street] = []
        for street in self.holeStreets:
            self.holecards[street] = {}  # dict from player names to holecards
        for street in self.discardStreets:
            self.discards[
                street
            ] = {}  # dict from player names to dicts by street ... of tuples ... of discarded holecards
        # Collections indexed by player names
        self.rakes: dict[str, Decimal] = {}
        self.stacks: dict[str, Decimal] = {}
        self.collected: list[Any] = []
        self.collectees: dict[str, Decimal] = {}
        self.koCounts: dict[str, int] = {}
        self.endBounty: dict[str, Decimal] = {}

        # Sets of players
        self.folded: set[str] = set()
        self.dealt: set[str] = set()  # 'dealt to' line to be printed
        self.shown: set[str] = set()  # cards were shown
        self.mucked: set[str] = set()  # cards were mucked at showdown
        self.sitout: set[str] = set()  # players sitting out or not dealt in

        # Things to do with money
        self.pot = Pot()
        self.totalpot: Decimal | None = None
        self.totalcollected: Decimal = Decimal("0.00")
        self.rake: Decimal | int | None = None
        self.bombPot = 0  # Bomb pot amount in cents (0 = no bomb pot)
        self.splashPot = 0  # Splash pot amount in cents (0 = no splash pot)
        # Who actually took the splash, in currency units. The total above says
        # what the room put on the table; this says where it went, which is the
        # only half the replayer can attribute to a seat.
        self.splashWinnings: dict[str, Decimal] = {}
        self.roundPenny = False
        self.fastFold = False
        # currency symbol for this hand
        curr = self.gametype.get("currency", "USD")
        if curr not in self.SYMBOL:
            curr = "USD"
        self.sym = self.SYMBOL[curr]  # save typing! delete this attr when done
        self.pot.setSym(self.sym)
        self.is_duplicate = False  # i.e. don't update hudcache if true

    def __str__(self) -> str:
        vars = (
            (("BB"), self.bb),
            (("SB"), self.sb),
            (("BUTTON POS"), self.buttonpos),
            (("HAND NO."), self.handid),
            (("SITE"), self.sitename),
            (("TABLE NAME"), self.tablename),
            (("HERO"), self.hero),
            (("MAX SEATS"), self.maxseats),
            (("LEVEL"), self.level),
            (("MIXED"), self.mixed),
            (("LAST BET"), self.lastBet),
            (("ACTION STREETS"), self.actionStreets),
            (("STREETS"), self.streets),
            (("ALL STREETS"), self.allStreets),
            (("COMMUNITY STREETS"), self.communityStreets),
            (("HOLE STREETS"), self.holeStreets),
            (("COUNTED SEATS"), self.counted_seats),
            (("DEALT"), self.dealt),
            (("SHOWN"), self.shown),
            (("MUCKED"), self.mucked),
            (("TOTAL POT"), self.totalpot),
            (("TOTAL COLLECTED"), self.totalcollected),
            (("RAKE"), self.rake),
            (("START TIME"), self.startTime),
            (("TOURNAMENT NO"), self.tourNo),
            (("TOURNEY ID"), self.tourneyId),
            (("TOURNEY TYPE ID"), self.tourneyTypeId),
            (("BUYIN"), self.buyin),
            (("BUYIN CURRENCY"), self.buyinCurrency),
            (("BUYIN CHIPS"), self.buyInChips),
            (("FEE"), self.fee),
            (("IS REBUY"), self.isRebuy),
            (("IS ADDON"), self.isAddOn),
            (("IS KO"), self.isKO),
            (("KO BOUNTY"), self.koBounty),
            (("IS MATRIX"), self.isMatrix),
            (("IS SHOOTOUT"), self.isShootout),
        )

        structs = (
            (("PLAYERS"), self.players),
            (("STACKS"), self.stacks),
            (("POSTED"), self.posted),
            (("POT"), self.pot),
            (("SEATING"), self.seating),
            (("GAMETYPE"), self.gametype),
            (("ACTION"), self.actions),
            (("COLLECTEES"), self.collectees),
            (("BETS"), self.bets),
            (("BOARD"), self.board),
            (("DISCARDS"), self.discards),
            (("HOLECARDS"), self.holecards),
            (("TOURNEYS PLAYER IDS"), self.tourneysPlayersIds),
        )
        result = ""
        for name, var in vars:
            result = result + f"\n{name} = " + pprint.pformat(var)

        for name, struct in structs:
            result = result + f"\n{name} =\n" + pprint.pformat(struct, 4)
        return result

    def addHoleCards(
        self,
        street,
        player,
        open=None,
        closed=None,
        shown=False,
        mucked=False,
        dealt=False,
    ) -> None:
        """Assigns observed holecards to a player.
        cards   list of card bigrams e.g. ['2h','Jc']
        player  (string) name of player
        shown   whether they were revealed at showdown
        mucked  whether they were mucked at showdown
        dealt   whether they were seen in a 'dealt to' line.
        """
        if closed is None:
            closed = []
        if open is None:
            open = []
        log.debug(
            f"Hand.addHoleCards open+closed: {open + closed}, player: {player}, shown: {shown}, mucked: {mucked}, dealt: {dealt}",
        )
        self.checkPlayerExists(player, "addHoleCards")

        if dealt:
            self.dealt.add(player)
        if shown:
            self.shown.add(player)
        if mucked:
            self.mucked.add(player)

        for i in range(len(closed)):
            if closed[i] in ("", "Xx", "Null", "null", "X"):
                closed[i] = "0x"

        try:
            self.holecards[street][player] = [open, closed]
        except KeyError as e:
            log.exception(f"'{self.handid}': Major failure while adding holecards: '{e}'")
            raise FpdbParseError

    def prepInsert(self, db, printtest=False) -> None:
        #####
        # Players, Gametypes, TourneyTypes are all shared functions that are needed for additional tables
        # These functions are intended for prep insert eventually
        #####
        if self.gametype.get("maxSeats") is None:
            if self.maxseats is not None:
                self.gametype["maxSeats"] = self.maxseats
        else:
            self.maxseats = self.gametype["maxSeats"]
        self.playerIds = db.getSqlPlayerIDs(
            [p[1] for p in self.players],
            self.siteId,
            self.hero,
        )
        self.dbid_gt = db.getSqlGameTypeId(
            self.siteId,
            self.gametype,
            printdata=printtest,
        )

        # Gametypes
        hilo = Card.games[self.gametype["category"]][2]

        self.gametyperow = (
            self.siteId,
            self.gametype["currency"],
            self.gametype["type"],
            self.gametype["base"],
            self.gametype["category"],
            self.gametype["limitType"],
            hilo,
            self.gametype["mix"],
            int(Decimal(self.gametype["sb"]) * 100),
            int(Decimal(self.gametype["bb"]) * 100),
            int(Decimal(self.gametype["bb"]) * 100),
            int(Decimal(self.gametype["bb"]) * 200),
            int(self.gametype["maxSeats"]),
            int(self.gametype["ante"] * 100),
            self.gametype["buyinType"],
            self.gametype["fast"],
            self.gametype["newToGame"],
            self.gametype["homeGame"],
            self.gametype["split"],
        )
        # Note: the above data is calculated in db.getGameTypeId
        #       Only being calculated above so we can grab the testdata
        if self.tourNo is not None:
            self.tourneyTypeId = db.getSqlTourneyTypeIDs(self)
            self.tourneyId = db.getSqlTourneyIDs(self)
            self.tourneysPlayersIds = db.getSqlTourneysPlayersIDs(self)

    def assembleHand(self) -> None:
        self.stats.getStats(self)
        self.hands = self.stats.getHands()
        self.handsplayers = self.stats.getHandsPlayers()
        self.handsactions = self.stats.getHandsActions()
        self.handsstove = self.stats.getHandsStove()
        self.handspots = self.stats.getHandsPots()

    def getHandId(self, db, id):
        if db.isDuplicate(
            self.siteId,
            self.hands["siteHandNo"],
            self.hands["heroSeat"],
            self.publicDB,
        ):
            log.debug(
                f"Hand.insert(): hid #: {self.hands['siteHandNo']} is a duplicate",
            )
            self.is_duplicate = True  # i.e. don't update hudcache
            if self.publicDB:
                msg = "{}-{}-{}".format(
                    str(self.siteId),
                    str(self.hands["siteHandNo"]),
                    self.hands["heroSeat"],
                )
                raise FpdbHandDuplicate(
                    msg,
                )
            msg = "{}-{}".format(str(self.siteId), str(self.hands["siteHandNo"]))
            raise FpdbHandDuplicate(
                msg,
            )
        self.dbid_hands = id
        self.hands["id"] = self.dbid_hands
        return id + db.hand_inc

    def insertHands(self, db, fileId, doinsert=False, printtest=False) -> None:
        """Function to insert Hand into database
        Should not commit, and do minimal selects. Callers may want to cache commits
        db: a connected Database object.
        """
        self.hands["gametypeId"] = self.dbid_gt
        self.hands["seats"] = len(self.playerIds)
        self.hands["fileId"] = fileId
        db.storeHand(self.hands, doinsert, printtest)
        db.storeBoards(self.dbid_hands, self.hands["boards"], doinsert)

    def insertHandsPlayers(self, db, doinsert=False, printtest=False) -> None:
        log.info(
            f"Entering insertHandsPlayers: doinsert={doinsert}, printtest={printtest}",
        )

        try:
            log.debug("Calling storeHandsPlayers for player data.")
            db.storeHandsPlayers(
                self.dbid_hands,
                self.playerIds,
                self.handsplayers,
                doinsert,
                printtest,
            )
        except Exception as e:  # intentional broad catch: DB adapter write failure is logged before re-raise.
            log.exception(f"Error in storeHandsPlayers: {e}")
            raise

        if self.handspots:
            log.debug(
                f"Sorting handspots: {len(self.handspots)} entries before sorting.",
            )
            self.handspots.sort(key=lambda x: x[1])
            log.debug(
                f"Sorting complete. Updating handspots with hand ID: {self.dbid_hands}.",
            )
            for ht in self.handspots:
                ht[0] = self.dbid_hands
            log.debug(f"Updated handspots: {self.handspots}")

        try:
            log.debug("Calling storeHandsPots for pot data.")
            db.storeHandsPots(self.handspots, doinsert)
            log.info("Successfully processed handspots.")
        except Exception as e:  # intentional broad catch: DB adapter write failure is logged before re-raise.
            log.exception(f"Error in storeHandsPots: {e}")
            raise

        log.info("Exiting insertHandsPlayers.")

    def insertPlayerAutoNotes(self, db, doinsert=False) -> None:
        """Generate and persist automatic notes for this imported hand."""
        from fpdb_3_legacy.AutoNotes import generate_for_hand

        notes = generate_for_hand(self, config=getattr(db, "config", None))
        db.storePlayerAutoNotes(notes, doinsert)

    def insertHandsActions(self, db, doinsert=False, printtest=False) -> None:
        """Function to inserts HandsActions into database."""
        if self.saveActions:
            db.storeHandsActions(
                self.dbid_hands,
                self.playerIds,
                self.handsactions,
                doinsert,
                printtest,
            )

    def insertHandsStove(self, db, doinsert=False) -> None:
        """Function to inserts HandsStove into database."""
        if self.handsstove:
            for hs in self.handsstove:
                hs[0] = self.dbid_hands
        db.storeHandsStove(self.handsstove, doinsert)

    def insertHandsShowdown(self, db, doinsert=False) -> None:
        """Persist parsed showdown combinations (and winning cards) per player.

        Reuses showdownStrings / winningHand collected by the site parser so
        the replayer (which rebuilds hands from the DB) can label and highlight
        the winning combination.
        """
        rows = []
        names = set(self.showdownStrings) | set(self.winningHand)
        for name in names:
            pid = self.playerIds.get(name)
            if pid is None:
                continue
            combo = self.showdownStrings.get(name)
            cards = self.winningHand.get(name)
            cards_str = " ".join(cards) if cards else None
            if combo is None and cards_str is None:
                continue
            rows.append([self.dbid_hands, pid, combo, cards_str])
        if rows:
            db.storeHandsShowdown(rows, doinsert)
        elif doinsert:
            # Flush any buffered rows from previous hands in this batch.
            db.storeHandsShowdown([], doinsert)

    def insertHandsCashout(self, db, doinsert=False) -> None:
        """Persist per-player EV cashout amounts/fees."""
        rows = []
        names = set(self.cashOutAmounts) | set(self.cashOutFees)
        for name in names:
            pid = self.playerIds.get(name)
            if pid is None:
                continue
            amount = self.cashOutAmounts.get(name)
            fee = self.cashOutFees.get(name)
            rows.append(
                [
                    self.dbid_hands,
                    pid,
                    str(amount) if amount is not None else None,
                    str(fee) if fee is not None else None,
                ]
            )
        if rows:
            db.storeHandsCashout(rows, doinsert)
        elif doinsert:
            db.storeHandsCashout([], doinsert)

    def updateTourneyResults(self, db) -> None:
        """Function to update Tourney Bounties if any."""
        db.updateTourneyPlayerBounties(self)

    def updateHudCache(self, db, doinsert=False) -> None:
        """Function to update the HudCache."""
        if self.callHud:
            db.storeHudCache(
                self.dbid_gt,
                self.gametype,
                self.playerIds,
                self.startTime,
                self.handsplayers,
                doinsert,
            )

    def updateSessionsCache(self, db, tz, doinsert=False) -> None:
        """Function to update the Sessions."""
        if self.cacheSessions:
            heroes = [next(iter(self.playerIds.values()))]
            db.storeSessions(
                self.dbid_hands,
                self.playerIds,
                self.startTime,
                self.tourneyId,
                heroes,
                tz,
                doinsert,
            )
            db.storeSessionsCache(
                self.dbid_hands,
                self.playerIds,
                self.startTime,
                self.dbid_gt,
                self.gametype,
                self.handsplayers,
                heroes,
                doinsert,
            )
            db.storeTourneysCache(
                self.dbid_hands,
                self.playerIds,
                self.startTime,
                self.tourneyId,
                self.gametype,
                self.handsplayers,
                heroes,
                doinsert,
            )

    def updateCardsCache(self, db, tz, doinsert=False) -> None:
        """Function to update the CardsCache."""
        if self.cacheSessions:  # and self.hero in self.playerIds:
            heroes = [next(iter(self.playerIds.values()))]
            db.storeCardsCache(
                self.dbid_hands,
                self.playerIds,
                self.startTime,
                self.dbid_gt,
                self.tourneyTypeId,
                self.handsplayers,
                heroes,
                tz,
                doinsert,
            )

    def updatePositionsCache(self, db, tz, doinsert=False) -> None:
        """Function to update the PositionsCache."""
        if self.cacheSessions:  # and self.hero in self.playerIds:
            heroes = [next(iter(self.playerIds.values()))]
            db.storePositionsCache(
                self.dbid_hands,
                self.playerIds,
                self.startTime,
                self.dbid_gt,
                self.tourneyTypeId,
                self.handsplayers,
                self.hands,
                heroes,
                tz,
                doinsert,
            )

    def select(self, db, handId) -> None:
        """Function to create Hand object from database."""
        c = db.get_cursor()
        q = db.sql.query["playerHand"]
        q = q.replace("%s", db.sql.query["placeholder"])

        c.execute(f"select heroseat from Hands where id = {handId}")
        heroSeat = c.fetchone()[0]

        # PlayerStacks
        c.execute(q, (handId,))
        # See NOTE: below on what this does.

        # Descriptor must be lowercase: postgres returns lowercase, SQLite preserves case
        rows = c.fetchall()
        col_names = [col[0].lower() for col in c.description]
        player_rows = [dict(zip(col_names, row, strict=False)) for row in rows]

        # Resolve hero name first
        hero_name = None
        for row in player_rows:
            if row["seatno"] == heroSeat:
                hero_name = row["name"]
                break
        self.hero = hero_name or ""

        for row in player_rows:
            self.addPlayer(
                row["seatno"],
                row["name"],
                str(row["chips"]),
                str(row["position"]),
                row["sitout"],
                str(row["bounty"]),
            )
            cardlist = [Card.valueSuitFromCard(row[f"card{i}"]) for i in range(1, 21)]
            # mucked/shown/dealt is not in the database, use mucked for villain and dealt for hero
            if row["seatno"] == heroSeat:
                dealt = True
                mucked = False
            else:
                dealt = False
                mucked = True
            game = Card.games[self.gametype["category"]]
            if game[0] == "hold" and cardlist[0] != "":
                # Where this game keeps its hole cards, not where most games
                # do. All-in or Fold deals the flop before the betting and has
                # no preflop street at all, so rebuilding one of its hands
                # from the database asked for a street that does not exist and
                # every such hand was dropped by the viewer and the replayer.
                self.addHoleCards(
                    self.holeStreets[0] if getattr(self, "holeStreets", None) else "PREFLOP",
                    row["name"],
                    closed=cardlist[0 : game[5][0][1]],
                    shown=False,
                    mucked=mucked,
                    dealt=dealt,
                )
            elif game[0] == "stud" and cardlist[2] != "":
                streets = {v: k for (k, v) in list(game[3].items())}
                for streetidx, hrange in enumerate(game[5]):
                    # Check if this is SEVENTH street for 7 Card Stud
                    if streets[streetidx] == "SEVENTH":
                        if row["name"] == self.hero:
                            open_cards = [cardlist[6]]
                            closed_cards = []
                        else:
                            open_cards = []
                            closed_cards = [cardlist[6]]
                    else:
                        open_cards = [cardlist[hrange[1] - 1]]
                        closed_cards = cardlist[0 : hrange[1] - 1]

                    self.addHoleCards(
                        streets[streetidx],
                        row["name"],
                        open=open_cards,
                        closed=closed_cards,
                        shown=False,
                        mucked=False,
                    )
            elif game[0] == "draw":
                streets = {v: k for (k, v) in list(game[3].items())}
                for streetidx, hrange in enumerate(game[5]):
                    self.addHoleCards(
                        streets[streetidx],
                        row["name"],
                        closed=cardlist[hrange[0] : hrange[1]],
                        shown=False,
                        mucked=mucked,
                        dealt=dealt,
                    )
            if row["winnings"] > 0:
                # Use addCashOutPot for cash outs to avoid adding to totalcollected
                if row.get("iscashout", False):  # Handle case where column might not exist yet
                    self.addWonPot(row["name"], str(row["winnings"]), is_cashout=True)
                else:
                    self.addWonPot(row["name"], str(row["winnings"]))
            if row["position"] == "0":
                # position 0 is the button, heads-up there is no position 0
                self.buttonpos = row["seatno"]
            elif row["position"] == "B":
                # Headsup the BB is the button, only set the button position if it's not set before
                if self.buttonpos is None or self.buttonpos == 0:
                    self.buttonpos = row["seatno"]

        # HandInfo
        q = db.sql.query["singleHand"]
        q = q.replace("%s", db.sql.query["placeholder"])
        c.execute(q, (handId,))

        # NOTE: This relies on row_factory = sqlite3.Row (set in connect() params)
        #       Need to find MySQL and Postgres equivalents
        #       MySQL maybe: cursorclass=MySQLdb.cursors.DictCursor
        # res = c.fetchone()

        # Using row_factory is global, and affects the rest of fpdb. The following 2 line achieves
        # a similar result

        # Descriptor must be lowercase: postgres returns lowercase, SQLite preserves case
        rows = c.fetchall()
        col_names = [col[0].lower() for col in c.description]
        hand_info = dict(zip(col_names, rows[0], strict=False))

        self.tablename = hand_info["tablename"]
        self.handid = hand_info["sitehandno"]
        # Bomb/splash pot markers (cents) for the replayer overlay; older DBs
        # created before these columns simply return nothing, keeping the 0 default.
        self.bombPot = hand_info.get("bombpot", 0) or 0
        self.splashPot = hand_info.get("splashpot", 0) or 0
        # self.startTime currently unused in the replayer and commented out.
        # However a startTime is needed for a valid output by writeHand:
        if isinstance(hand_info["starttime"], datetime.datetime):
            self.startTime = hand_info["starttime"]
        else:
            # Handle string formats from different DB backends
            # SQLite default: %Y-%m-%d %H:%M:%S or %Y-%m-%d %H:%M:%S.%f
            # Others might include timezone: %Y-%m-%d %H:%M:%S+00:00
            formats = [
                "%Y-%m-%d %H:%M:%S+00:00",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
            ]
            parsed = False
            for fmt in formats:
                try:
                    self.startTime = datetime.datetime.strptime(hand_info["starttime"], fmt)
                    parsed = True
                    break
                except ValueError:
                    continue

            if not parsed:
                log.warning(
                    "Could not parse starttime: '%s', defaulting to 1970-01-01",
                    hand_info["starttime"],
                )
                self.startTime = datetime.datetime.strptime(
                    "1970-01-01 12:00:00",
                    "%Y-%m-%d %H:%M:%S",
                )

        cards = list(
            map(
                Card.valueSuitFromCard,
                [
                    hand_info["boardcard1"],
                    hand_info["boardcard2"],
                    hand_info["boardcard3"],
                    hand_info["boardcard4"],
                    hand_info["boardcard5"],
                ],
            ),
        )
        if cards[0]:
            self.setCommunityCards("FLOP", cards[0:3])
        if cards[3]:
            self.setCommunityCards("TURN", [cards[3]])
        if cards[4]:
            self.setCommunityCards("RIVER", [cards[4]])

        if hand_info["runittwice"] or self.gametype["split"]:
            # Fetch the boards first so we know how many runs there were
            # (run-it-twice and run-it-three both come through here).
            q = db.sql.query["singleHandBoards"]
            q = q.replace("%s", db.sql.query["placeholder"])
            c.execute(q, (handId,))
            rows = c.fetchall()
            col_names = [col[0].lower() for col in c.description]
            boards = [dict(zip(col_names, row, strict=False)) for row in rows]

            # Extend the streets for the actual number of runs.
            self.runItTimes = max(2, len(boards)) if boards else 2
            run_it_streets = []
            for run in range(1, self.runItTimes + 1):
                run_it_streets += [f"FLOP{run}", f"TURN{run}", f"RIVER{run}"]
            for street in run_it_streets:
                if street not in self.actionStreets:
                    self.actionStreets.append(street)
                    self.bets[street] = {}
                    self.lastBet[street] = 0
                    self.actions[street] = []
                    self.board[street] = []
                    # Add existing players to new street
                    for player_info in self.players:
                        player_name = player_info[1]  # player name is at index 1
                        self.bets[street][player_name] = []
                if street not in self.allStreets:
                    self.allStreets.append(street)
                if street not in self.streets:
                    self.streets[street] = ""

            for b in boards:
                cards = list(
                    map(
                        Card.valueSuitFromCard,
                        [
                            b["boardcard1"],
                            b["boardcard2"],
                            b["boardcard3"],
                            b["boardcard4"],
                            b["boardcard5"],
                        ],
                    ),
                )
                if cards[0]:
                    street = "FLOP" + str(b["boardid"])
                    self.setCommunityCards(street, cards[0:3])
                    if "FLOP" in self.allStreets:
                        self.allStreets.remove("FLOP")
                    if street not in self.allStreets:
                        self.allStreets.append(street)
                    self.actions[street] = []
                if cards[3]:
                    street = "TURN" + str(b["boardid"])
                    self.setCommunityCards(street, [cards[3]])
                    if "TURN" in self.allStreets:
                        self.allStreets.remove("TURN")
                    if street not in self.allStreets:
                        self.allStreets.append(street)
                    self.actions[street] = []
                if cards[4]:
                    street = "RIVER" + str(b["boardid"])
                    self.setCommunityCards(street, [cards[4]])
                    if "RIVER" in self.allStreets:
                        self.allStreets.remove("RIVER")
                    if street not in self.allStreets:
                        self.allStreets.append(street)
                    self.actions[street] = []

        # playersVpi | playersAtStreet1 | playersAtStreet2 | playersAtStreet3 |
        # playersAtStreet4 | playersAtShowdown | street0Raises | street1Raises |
        # street2Raises | street3Raises | street4Raises | street1Pot | street2Pot |
        # street3Pot | street4Pot | showdownPot | comment | commentTs | texture

        # Actions
        q = db.sql.query["handActions"]
        q = q.replace("%s", db.sql.query["placeholder"])
        c.execute(q, (handId,))

        # Descriptor must be lowercase: postgres returns lowercase, SQLite preserves case
        rows = c.fetchall()
        col_names = [col[0].lower() for col in c.description]
        action_rows = [dict(zip(col_names, row, strict=False)) for row in rows]
        for row in action_rows:
            name = row["name"]
            street = row["street"]
            act = row["actionid"]
            # allin True/False if row['allIn'] == 0
            bet = str(row["bet"])
            street = self.allStreets[int(street) + 1]
            discards = row["cardsdiscarded"]
            log.debug(
                f"Hand.select():: name: '{name}' street: '{street}' act: '{act}' bet: '{bet}'",
            )
            if act == 1:  # Ante
                self.addAnte(name, bet)
            elif act == 2:  # Small Blind
                self.addBlind(name, "small blind", bet)
            elif act == 3:  # Second small blind
                self.addBlind(name, "secondsb", bet)
            elif act == 4:  # Big Blind
                self.addBlind(name, "big blind", bet)
            elif act == 5:  # Post both blinds
                self.addBlind(name, "both", bet)
            elif act == 6:  # Call
                self.addCall(street, name, bet)
            elif act == 7:  # Raise
                self.addRaiseBy(street, name, bet)
            elif act == 8:  # Bet
                self.addBet(street, name, bet)
            elif act == 9:  # Stands pat
                self.addStandsPat(street, name, discards)
            elif act == 10:  # Fold
                self.addFold(street, name)
            elif act == 11:  # Check
                self.addCheck(street, name)
            elif act == 12:  # Discard
                self.addDiscard(street, name, row["numdiscarded"], discards)
            elif act == 13:  # Bringin
                getattr(self, "addBringIn")(name, bet)
            elif act == 14:  # Complete
                getattr(self, "addComplete")(street, name, bet)
            elif act == 15:
                self.addBlind(name, "straddle", bet)
            elif act == 16:
                self.addBlind(name, "button blind", bet)
            elif act == 17:  # Cashout
                self.addCashout(street, name)
            else:
                log.warning(f"unknown action: '{act}'")

        self.totalPot()
        if self.totalpot is None:
            raise FpdbParseError("Pot calculation did not produce a total")
        self.rake = self.totalpot - self.totalcollected

        # Restore showdown combinations / winning cards parsed at import time
        # (stored in HandsShowdown) so the replayer can label and highlight them.
        try:
            showdown = db.get_hands_showdown(handId)
        except Exception:  # noqa: BLE001 - legacy DB without the table.
            showdown = {}
        for name, (combo, cards) in showdown.items():
            if combo:
                self.showdownStrings[name] = combo
            if cards:
                self.winningHand[name] = cards.split(" ")

        # Restore EV cashout amounts/fees (stored in HandsCashout).
        try:
            cashouts = db.get_hands_cashout(handId)
        except Exception:  # noqa: BLE001 - legacy DB without the table.
            cashouts = {}
        for name, (amount, fee) in cashouts.items():
            try:
                if amount is not None:
                    self.cashOutAmounts[name] = Decimal(str(amount))
                if fee is not None:
                    self.cashOutFees[name] = Decimal(str(fee))
            except (ValueError, ArithmeticError):
                continue
        if cashouts:
            self.cashedOut = True

        # Restore who collected the splash (stored in cents on HandsPlayers).
        try:
            splash = db.get_hands_splash(handId)
        except Exception:  # noqa: BLE001 - legacy DB without the column.
            splash = {}
        for name, amount in splash.items():
            try:
                self.splashWinnings[name] = Decimal(str(amount)) / 100
            except (ValueError, ArithmeticError):
                continue

    def addPlayer(self, seat, name, chips, position=None, sitout=False, bounty=None) -> None:
        """Adds a player to the hand, and initialises data structures indexed by player.
        seat    (int) indicating the seat
        name    (string) player name
        chips   (string) the chips the player has at the start of the hand (can be None)
        position     (string) indicating the position of the player (S,B, 0-7) (optional, not needed on Hand import from Handhistory).
        If a player has None chips he won't be added.
        """
        if len(self.players) > 0 and seat in [p[0] for p in self.players]:
            raise FpdbHandPartial(
                "addPlayer: " + ("Can't have 2 players in the same seat!") + f": '{self.handid}'",
            )

        log.debug(f"add Player: {seat} {name} ({chips})")
        if chips is not None:
            chips = chips.replace(",", "")  # some sites have commas
            self.players.append([seat, name, chips, position, bounty])
            self.stacks[name] = Decimal(chips)
            self.pot.addPlayer(name)
            for street in self.actionStreets:
                self.bets[street][name] = []
            if sitout:
                self.sitout.add(name)

    def removePlayer(self, name) -> None:
        if self.stacks.get(name):
            self.players = [p for p in self.players if p[1] != name]
            del self.stacks[name]
            self.pot.removePlayer(name)
            for street in self.actionStreets:
                del self.bets[street][name]
            self.sitout.discard(name)

    def addStreets(self, match) -> None:
        # go through m and initialise actions to empty list for each street.
        if match:
            # print('if match', match)
            # print("if match.gr:",match.groupdict())
            # log.debug(f"type self.streets: {type(self.streets)}")
            self.streets.update(match.groupdict())
            log.debug(f"streets: {self.streets!s}")
            log.debug(f"markStreets:\n{self.streets!s}")
        else:
            tmp = self.handText[0:100]
            self.cancelled = True
            raise FpdbHandPartial(
                (f"Streets didn't match - Assuming hand '{self.handid}' was cancelled.")
                + " "
                + (f"First 100 characters: {tmp}"),
            )

    def checkPlayerExists(self, player, source=None) -> None:
        # Fast path, because this function is called ALL THE TIME.
        if player in self.player_exists_cache:
            return

        if player not in (p[1] for p in self.players):
            if source is not None:
                log.error(f"Hand.{source}: '{self.handid}' unknown player: '{player}'")
            raise FpdbParseError
        self.player_exists_cache.add(player)

    def setCommunityCards(self, street, cards) -> None:
        log.debug(f"setCommunityCards {street} {cards}")
        self.board[street] = [self.card(c) for c in cards]

    def card(self, c):
        """Upper case the ranks but not suits, 'atjqk' => 'ATJQK'."""
        for k, v in list(self.UPS.items()):
            c = c.replace(k, v)
        return c

    def addAllIn(self, street, player, amount) -> None:
        """For sites (currently only Merge & Microgaming) which record "all in" as a special action,
        which can mean either "calls and is all in" or "raises all in".
        """
        self.checkPlayerExists(player, "addAllIn")
        amount = amount.replace(",", "")  # some sites have commas
        Ai = Decimal(amount)
        Bp = self.lastBet[street]
        Bc = sum(self.bets[street][player])
        C = Bp - Bc
        if Ai <= C:
            self.addCall(street, player, amount)
        elif Bp == 0:
            self.addBet(street, player, amount)
        else:
            Rb = Ai - C
            Rt = Bp + Rb
            self._addRaise(street, player, C, Rb, Rt)

    def addSTP(self, amount) -> None:
        amount = amount.replace(",", "")  # some sites have commas
        amount = Decimal(amount)
        self.pot.setSTP(amount)

    def addAnte(self, player, ante) -> None:
        log.debug(f"BLINDSANTES {player} antes {ante}")
        if player is not None:
            ante = ante.replace(",", "")  # some sites have commas
            self.checkPlayerExists(player, "addAnte")
            ante = Decimal(ante)
            self.bets["BLINDSANTES"][player].append(ante)
            self.stacks[player] -= ante
            act = (player, "ante", ante, self.stacks[player] == 0)
            self.actions["BLINDSANTES"].append(act)
            self.pot.addCommonMoney(player, ante)
            self.pot.addAntes(player, ante)
            if "ante" not in list(self.gametype.keys()) or self.gametype["ante"] < ante:
                self.gametype["ante"] = ante

    # I think the antes should be common money, don't have enough hand history to check

    def addBlind(self, player, blindtype, amount) -> None:
        # if player is None, it's a missing small blind.
        # The situation we need to cover are:
        # Player in small blind posts
        #   - this is a bet of 1 sb, as yet uncalled.
        # Player in the big blind posts
        #   - this is a call of 1 sb and a raise to 1 bb
        #
        log.debug(f"addBlind: {player} posts {blindtype}, {amount}")
        if player is not None:
            self.checkPlayerExists(player, "addBlind")
            amount = amount.replace(",", "")  # some sites have commas
            amount = Decimal(amount)
            self.stacks[player] -= amount
            act = (player, blindtype, amount, self.stacks[player] == 0)
            self.actions["BLINDSANTES"].append(act)

            if blindtype == "both":
                # work with the real amount. limit games are listed as $1, $2, where
                # the SB 0.50 and the BB is $1, after the turn the minimum bet amount is $2....
                amount = Decimal(str(self.bb))
                sb = Decimal(str(self.sb))
                self.bets["BLINDSANTES"][player].append(sb)
                self.pot.addCommonMoney(player, sb)

            if blindtype == "secondsb":
                amount = Decimal(0)
                sb = Decimal(str(self.sb))
                self.bets["BLINDSANTES"][player].append(sb)
                self.pot.addCommonMoney(player, sb)

            street = "BLAH"

            if is_aof_category(self.gametype["category"]):
                street = "FLOP"
            elif self.gametype["base"] == "hold":
                street = "PREFLOP"
            elif self.gametype["base"] == "draw":
                street = "DEAL"

            self.bets[street][player].append(amount)
            self.pot.addMoney(player, amount)
            if amount > self.lastBet.get(street):
                self.lastBet[street] = amount
            self.posted = [*self.posted, [player, blindtype]]

    def addCall(self, street, player=None, amount=None) -> None:
        if amount is not None:
            amount = amount.replace(",", "")  # some sites have commas
        log.debug(f"{street} {player} calls {amount}")
        # Potentially calculate the amount of the call if not supplied
        # corner cases include if player would be all in
        if amount is not None:
            self.checkPlayerExists(player, "addCall")
            amount = Decimal(amount)
            self.bets[street][player].append(amount)
            if street in ("PREFLOP", "DEAL", "THIRD") and self.lastBet.get(street) < amount:
                self.lastBet[street] = amount
            self.stacks[player] -= amount
            act = (player, "calls", amount, self.stacks[player] == 0)
            self.actions[street].append(act)
            self.pot.addMoney(player, amount)

    def addCallTo(self, street, player=None, amountTo=None) -> None:
        if amountTo:
            amountTo = amountTo.replace(",", "")  # some sites have commas
        # Potentially calculate the amount of the callTo if not supplied
        # corner cases include if player would be all in
        if amountTo is not None:
            self.checkPlayerExists(player, "addCallTo")
            Bc = sum(self.bets[street][player])
            Ct = Decimal(amountTo)
            C = Ct - Bc
            amount = C
            self.bets[street][player].append(amount)
            self.stacks[player] -= amount
            act = (player, "calls", amount, self.stacks[player] == 0)
            self.actions[street].append(act)
            self.pot.addMoney(player, amount)

    def addRaiseBy(self, street, player, amountBy) -> None:
        """Add a raise by amountBy on [street] by [player]."""
        # Given only the amount raised by, the amount of the raise can be calculated by
        # working out how much this player has already in the pot
        #   (which is the sum of self.bets[street][player])
        # and how much he needs to call to match the previous player
        #   (which is tracked by self.lastBet)
        # let Bp = previous bet
        #     Bc = amount player has committed so far
        #     Rb = raise by
        # then: C = Bp - Bc (amount to call)
        #      Rt = Bp + Rb (raise to)
        #
        amountBy = amountBy.replace(",", "")  # some sites have commas
        self.checkPlayerExists(player, "addRaiseBy")
        Rb = Decimal(amountBy)
        Bp = self.lastBet[street]
        Bc = sum(self.bets[street][player])
        C = Bp - Bc
        Rt = Bp + Rb

        self._addRaise(street, player, C, Rb, Rt)

    def addCallandRaise(self, street, player, amount) -> None:
        """For sites which by "raises x" mean "calls and raises putting a total of x in the por"."""
        self.checkPlayerExists(player, "addCallandRaise")
        amount = amount.replace(",", "")  # some sites have commas
        CRb = Decimal(amount)
        Bp = self.lastBet[street]
        Bc = sum(self.bets[street][player])
        C = Bp - Bc
        Rb = CRb - C
        Rt = Bp + Rb

        self._addRaise(street, player, C, Rb, Rt)

    def addRaiseTo(self, street, player, amountTo) -> None:
        """Add a raise on [street] by [player] to [amountTo]."""
        self.checkPlayerExists(player, "addRaiseTo")
        amountTo = amountTo.replace(",", "")  # some sites have commas
        Bp = self.lastBet[street]
        Bc = sum(self.bets[street][player])
        Rt = Decimal(amountTo)
        C = Bp - Bc
        Rb = Rt - C - Bc
        self._addRaise(street, player, C, Rb, Rt)

    def _addRaise(self, street, player, C, Rb, Rt, action="raises") -> None:
        log.debug(f"{street} {player} raise {Rt}")
        self.bets[street][player].append(C + Rb)
        self.stacks[player] -= C + Rb
        act = (player, action, Rb, Rt, C, self.stacks[player] == 0)
        self.actions[street].append(act)
        # ``lastBet`` is the total amount to match on this street.  Keeping the
        # raise-to value here is required for the next player's call/raise math.
        self.lastBet[street] = Rt
        self.pot.addMoney(player, C + Rb)

    def addWonPot(self, player, amount, pot_type="main", is_cashout=False) -> None:
        """Determines who won what.
        player      (string) name of player
        amount      (Decimal) amount won.
        pot_type    (string) main/side/cashout
        """
        self.checkPlayerExists(player, "addWonPot")

        # If it's a cashout, use addCashOutPot instead to avoid side-effects on won hand logic
        if is_cashout:
            self.addCashOutPot(player, str(amount))
            return

        # Winnings are tracked on the Hand, not the Pot (which only tracks money put
        # IN: committed/common/antes). Mirror addCollectPot: coerce to Decimal before
        # arithmetic (Hand.select() passes amount as a str, which broke
        # `totalcollected += amount`) and record per-player winnings in collectees.
        self.collected.append([player, amount])
        amount = Decimal(amount)
        if player not in self.collectees:
            self.collectees[player] = amount
        else:
            self.collectees[player] += amount
        self.totalcollected += amount

    def addBet(self, street, player, amount) -> None:
        log.debug(f"{street} {player} bets {amount}")
        amount = amount.replace(",", "")  # some sites have commas
        amount = Decimal(amount)
        self.checkPlayerExists(player, "addBet")
        self.bets[street][player].append(amount)
        self.stacks[player] -= amount
        act = (player, "bets", amount, self.stacks[player] == 0)
        self.actions[street].append(act)
        self.lastBet[street] = amount
        self.pot.addMoney(player, amount)

    def addStandsPat(self, street, player, cards=None) -> None:
        self.checkPlayerExists(player, "addStandsPat")
        act = (player, "stands pat")
        self.actions[street].append(act)
        if cards:
            cards = cards.split(" ")
            self.addHoleCards(street, player, open=[], closed=cards)

    def addFold(self, street, player) -> None:
        log.debug(f"{street} {player} folds")
        self.checkPlayerExists(player, "addFold")
        if player in self.folded:
            return
        self.folded.add(player)
        self.pot.addFold(player)
        self.actions[street].append((player, "folds"))

    def addCheck(self, street, player) -> None:
        log.debug(f"{street} {player} checks")
        self.checkPlayerExists(player, "addCheck")
        self.actions[street].append((player, "checks"))

    def addCashout(self, street, player) -> None:
        log.debug(f"{street} {player} cashout")
        self.checkPlayerExists(player, "addCashout")
        self.actions[street].append((player, "cashout"))

    def discardDrawHoleCards(self, cards, player, street) -> None:
        log.debug(f"discardDrawHoleCards '{cards}' '{player}' '{street}'")
        self.discards[street][player] = {cards}

    def addDiscard(self, street, player, num, cards=None) -> None:
        self.checkPlayerExists(player, "addDiscard")
        act: tuple[Any, ...]
        if cards:
            act = (player, "discards", Decimal(num), cards)
            self.discardDrawHoleCards(cards, player, street)
        else:
            act = (player, "discards", Decimal(num))
        self.actions[street].append(act)

    def addCollectPot(self, player, pot) -> None:
        log.debug(f"{player} collected {pot}")
        self.checkPlayerExists(player, "addCollectPot")
        self.collected.append([player, pot])
        amount = Decimal(pot)
        if player not in self.collectees:
            self.collectees[player] = amount
        else:
            self.collectees[player] += amount

        # update collected pot
        self.totalcollected += amount
        log.debug(f"Updated totalcollected: {self.totalcollected}")

    def addCashOutPot(self, player, pot) -> None:
        """Records a cash out event for a player in the current hand.

        Cash out is an INSURANCE payout from the poker site, NOT pot winnings.
        It should still be tracked in collected/collectees for parser parity and
        UI display, but it must NOT affect totalcollected. Cash out amounts are
        also tracked separately in cashOutAmounts.

        Args:
            player: The name of the player cashing out.
            pot: The amount the player cashed out.

        Returns:
            None
        """
        log.debug(f"{player} cashed out for {pot}")
        self.checkPlayerExists(player, "addCashOutPot")
        amount = Decimal(pot)
        self.collected.append([player, pot])
        if player not in self.collectees:
            self.collectees[player] = amount
        else:
            self.collectees[player] += amount

        # Store cash out amount separately for dedicated reporting.
        if player not in self.cashOutAmounts:
            self.cashOutAmounts[player] = amount
        else:
            self.cashOutAmounts[player] += amount

        # NOTE: Do NOT add to totalcollected for cash outs.
        log.debug("Cash out recorded without changing totalcollected")

    def addUncalled(self, street, player, amount) -> None:
        log.debug(f"{street} {player} uncalled {amount}")
        amount = amount.replace(",", "")  # some sites have commas
        amount = Decimal(amount)
        self.checkPlayerExists(player, "addUncalled")
        self.stacks[player] += amount
        self.pot.removeMoney(player, amount)

    def sittingOut(self) -> None:
        dealtIn = set()
        for street in self.actionStreets:
            for act in self.actions[street]:
                dealtIn.add(act[0])
        for player in list(self.collectees.keys()):
            dealtIn.add(player)
        for player in self.dealt:
            dealtIn.add(player)
        # A player who showed cards at showdown participated, even if their only
        # wager was an all-in blind that wasn't recorded as an action (e.g. a
        # Bovada heads-up "Big Blind : All-in" hand). Without this they get
        # removed and a complete hand is mis-flagged as a cancelled one.
        for player in self.shown:
            dealtIn.add(player)
        for p in list(self.players):
            if p[1] not in dealtIn:
                if self.gametype["type"] == "tour":
                    self.sitout.add(p[1])
                else:
                    self.removePlayer(p[1])
        if len(self.players) < 2:
            msg = f"Less than 2 players - Assuming hand '{self.handid}' was cancelled."
            raise FpdbHandPartial(
                msg,
            )

    def setUncalledBets(self, value) -> None:
        self.uncalledbets = value

    def calculate_net_collected(self) -> None:
        """Calculate the net collected amount for each player."""
        log.debug("Starting net collected calculation...")

        self.net_collected = {}
        for player in self.pot.committed:
            collected = self.collectees.get(player, Decimal("0.00"))
            uncalled_bets = self.pot.returned.get(player, Decimal("0.00"))
            committed = self.pot.committed.get(player, Decimal("0.00"))
            self.net_collected[player] = collected + uncalled_bets - committed
            log.debug(f"Net collected for {player}: {self.net_collected[player]:.2f}")

        log.debug("Net collected calculation complete.")

    def totalPot(self):
        """Calculates the pots (main and side pots), handles uncalled bets, common money (antes, etc.),
        and the STP amount, then determines the rake. Updates self.totalpot, self.rake, and self.pot.pots.

        Modification:
        If the game is a tournament ('self.gametype["type"] == "tour"'), we do not recalculate
        rake on a per-hand basis. Instead, we set self.rake to 0. This avoids the issue of
        exceeding collected amounts in tournament scenarios.

        If totalpot has already been set by the parser (e.g., SealsWithClubs), we trust that value
        and skip recalculation.
        """
        log.debug("Starting pot calculation...")

        # If totalpot has already been set by the parser, trust it
        if self.totalpot is not None and self.totalpot > 0:
            log.debug(f"Total pot already set by parser: {self.totalpot}")

            # Check if rake was explicitly parsed from hand text
            if hasattr(self, "rake_parsed") and self.rake_parsed and self.rake is not None:
                log.debug(f"Rake already parsed from hand text: {self.rake}")
                # When both pot and rake are parsed, skip validation
                return self.totalpot

            # Still need to calculate rake if not set
            if self.rake is None:
                if self.gametype["type"] == "tour":
                    self.rake = Decimal("0.00")
                    log.debug("Tournament detected, rake set to 0.")
                    if self.totalcollected > 0 and self.totalpot != self.totalcollected:
                        log.warning(
                            f"Auto-balancing tournament totalpot ({self.totalpot}) to match totalcollected ({self.totalcollected})"
                        )
                        self.totalpot = self.totalcollected
                elif self.totalpot > self.totalcollected:
                    self.rake = self.totalpot - self.totalcollected
                    log.debug(f"Calculated rake: {self.rake}")
                else:
                    self.rake = Decimal("0.00")
                    log.debug("No rake detected.")

            return self.totalpot

        # Basic verification
        if not isinstance(self.pot.committed, dict) or len(self.pot.committed) == 0:
            log.error("self.pot.committed is not initialized or empty.")
            msg = "self.pot.committed is missing or improperly initialized."
            raise FpdbParseError(
                msg,
            )

        # Convert and filter out non-positive commits
        try:
            commitsall = [(Decimal(v), k) for (k, v) in self.pot.committed.items() if Decimal(v) > 0]
        except HAND_DECIMAL_ERRORS as e:
            log.exception(f"Error while preparing commitsall: {e}")
            msg = f"Invalid data in self.pot.committed: {e}"
            raise FpdbParseError(msg)

        commitsall.sort(key=lambda x: x[0])
        log.debug(f"Initial committed values (sorted): {commitsall}")

        # Initializations
        self.totalpot = Decimal("0.00")
        self.pot.pots = []
        if self.totalcollected is None:
            log.warning(
                "totalcollected was None during totalPot calculation. Setting it to 0.00",
            )
            self.totalcollected = Decimal("0.00")

        def create_pot_from_value(value, calls):
            """Takes a specified pot value (value) and a list of (amount, player) tuples (calls).
            It creates a pot containing the minimum between 'value' and each player's committed amount.

            Returns:
                The updated list of commitments after forming this pot.

            """
            pot_val = sum(min(v, value) for (v, k) in calls)
            self.totalpot += pot_val
            participants = {k for (v, k) in calls}
            self.pot.pots.append((pot_val, participants))
            log.debug(f"Created pot: Value={pot_val}, Participants={participants}")

            # Update remaining commitments
            updated = []
            for v, kk in calls:
                nv = v - value
                if nv > 0:
                    updated.append((nv, kk))
            updated.sort(key=lambda x: x[0])
            return updated

        def handle_leftover(calls):
            """If after forming pots there's only one player left with extra chips committed,
            and these are not matched by others, we have a leftover.

            If totalcollected > totalpot, we can form a final solo pot from leftover.
            Otherwise, we must return the surplus to the player (uncalled bet).
            """
            leftover_sum = sum(v for (v, k) in calls)
            # self.totalpot does not yet include common money (antes / dead blinds)
            # or the STP — those are added after this loop. Account for them here so
            # an uncalled bet isn't mistaken for a collectable solo pot (e.g. small
            # stud hands where the last bet is folded to and the site prints no
            # "Uncalled bet returned" line). Otherwise the surplus inflates the pot
            # and the hand is rejected as "rake > 25%".
            totalpot = self.totalpot
            if totalpot is None:
                raise FpdbParseError("Pot total was cleared during calculation")
            effective_pot = totalpot + sum(self.pot.common.values()) + self.pot.stp
            diff = self.totalcollected - effective_pot
            log.debug(
                f"Single-player leftover detected. diff={diff}, leftover={leftover_sum}",
            )

            if diff > 0:
                # Create a final solo pot from this leftover
                participant = {calls[0][1]}
                self.totalpot += leftover_sum
                self.pot.pots.append((leftover_sum, participant))
                log.debug(
                    f"Formed final solo pot from leftover: {leftover_sum}, Participant={participant}",
                )
                return []
            # Surplus must be returned to the player as uncalled bet
            player = calls[0][1]
            # Take it out of pot.committed too, exactly as the parser path does
            # (Hand.addUncalled -> Pot.removeMoney). DerivedStats derives
            # totalProfit from committed and documents that the uncalled bet has
            # already been removed from it, so recording the return here without
            # touching committed left the player paying for a bet nobody called:
            # a hand won without showdown was reported as a loss.
            # Sites whose history prints an "Uncalled bet returned" line have
            # already removed it before totalPot() runs, so no leftover is found
            # here and this stays idempotent.
            self.pot.committed[player] -= leftover_sum
            self.pot.returned[player] = self.pot.returned.get(player, Decimal("0.00")) + leftover_sum
            log.debug(f"Uncalled bet returned to {player}: {leftover_sum}")
            return []

        # Creating the pots
        try:
            while commitsall:
                # If a single player is the only one with chips committed, everyone
                # else folded to their bet, so it is entirely uncalled — return it
                # (or form a solo pot) rather than building a pot with one
                # contributor. This also covers a bring-in/bet folded to with no
                # explicit "Uncalled bet returned" line.
                if len(commitsall) == 1:
                    commitsall = handle_leftover(commitsall)
                    break
                # Cut the next pot at the smallest remaining commitment: everyone
                # still in matches it, and whoever committed exactly that much is
                # all in, so the players above him form the next side pot.
                # A fractional amount used to be sliced into one 1.00 pot per whole
                # unit plus the remainder. Every slice has the same participants,
                # so the totals came out identical while the pot count grew with the
                # stakes: a $1,860.50 all-in produced 1,861 pots, each one costing a
                # board evaluation and a HandsPots row (a $500k play-money hand was
                # far worse). Cutting once is equivalent and bounded by the number
                # of distinct commitment levels.
                v1 = commitsall[0][0]
                commitsall = create_pot_from_value(v1, commitsall)
                if len(commitsall) == 1:
                    # Only one player left => handle leftover
                    commitsall = handle_leftover(commitsall)
                if not commitsall:
                    break

            # Add common money and STP to the total pot
            self.totalpot += sum(self.pot.common.values()) + self.pot.stp
            log.debug(f"Total pot after adding common money: {self.totalpot}")

            log.debug(f"Total collected amount: {self.totalcollected}")
            log.debug(f"Total pot amount: {self.totalpot}")

            # If this is a tournament, do not calculate rake here.
            # Tournaments typically do not have per-hand rake in the traditional sense.
            if self.gametype["type"] == "tour":
                self.rake = Decimal("0.00")
                log.debug("Tournament detected, rake set to 0.")
                if self.totalcollected > 0 and self.totalpot != self.totalcollected:
                    log.warning(
                        f"Auto-balancing tournament totalpot ({self.totalpot}) to match totalcollected ({self.totalcollected})"
                    )
                    self.totalpot = self.totalcollected
                return self.totalpot

            # For cash games (non-tournaments), handle rake calculation
            if self.totalpot > self.totalcollected:
                # Rake scenario: Rake = totalpot - totalcollected
                self.rake = self.totalpot - self.totalcollected
                log.debug(f"Rake scenario, Rake={self.rake}")
                return self.totalpot
            if self.totalpot == self.totalcollected:
                # Perfect match, no rake
                self.rake = Decimal("0.00")
                log.debug("Exact match between totalpot and totalcollected, rake=0")
                return self.totalpot
            # totalcollected > totalpot is an error scenario
            # Exception for special cases and hand viewing
            if (self.sitename == "Bovada" and hasattr(self, "isZonePoker") and self.isZonePoker) or (
                hasattr(self, "rake") and self.rake is not None
            ):
                # For Zone Poker hands or hands with pre-set rake, use collected amount as the pot total
                log.warning(
                    f"Hand {self.handid}: collected amount exceeds calculated pot, using collected amount as pot total"
                )
                self.totalpot = self.totalcollected
                if not hasattr(self, "rake") or self.rake is None:
                    self.rake = Decimal("0.00")  # Rake already deducted or calculated elsewhere
                return self.totalpot

            # For hand viewing/display, be more tolerant
            log.warning(
                f"Collected amount ({self.totalcollected}) exceeds total pot ({self.totalpot}) for hand {self.handid}, adjusting for display",
            )
            # Use collected amount as pot total for display purposes
            self.totalpot = self.totalcollected
            self.rake = Decimal("0.00")  # Assume rake already deducted
            return self.totalpot

        except Exception as e:  # intentional broad catch: pot calculation normalizes failures to FpdbParseError.
            log.exception(f"Pot calculation failed: {e}")
            msg = f"Error in pot calculation: {e!s}"
            raise FpdbParseError(msg)

    def getGameTypeAsString(self) -> str:
        """Map the tuple self.gametype onto the pokerstars string describing it."""
        # currently it appears to be something like ["ring", "hold", "nl", sb, bb]:
        gs = {
            "holdem": "Hold'em",
            "omahahi": "Omaha",
            "5_omahahi": "5 Card Omaha",
            "6_omahahi": "6 Card Omaha",
            "fusion": "Fusion",
            "omahahilo": "Omaha Hi/Lo",
            "razz": "Razz",
            "studhi": "7 Card Stud",
            "studhilo": "7 Card Stud Hi/Lo",
            "fivedraw": "5 Card Draw",
            "27_1draw": "Single Draw 2-7 Lowball",
            "27_3draw": "Triple Draw 2-7 Lowball",
            "5_studhi": "5 Card Stud",
            "badugi": "Badugi",
            "aof_omaha": "All-in or Fold Omaha",
            "aof_holdem": "All-in or Fold Hold'em",
        }
        ls = {
            "nl": "No Limit",
            "pl": "Pot Limit",
            "fl": "Limit",
            "cn": "Cap No Limit",
            "cp": "Cap Pot Limit",
        }

        log.debug(f"gametype: {self.gametype}")
        return "{} {}".format(
            gs[self.gametype["category"]],
            ls[self.gametype["limitType"]],
        )

    def printHand(self) -> None:
        self.writeHand(sys.stdout)

    def actionString(self, act, street=None) -> str | None:
        log.debug(f"Hand.actionString(act={act}, street={street})")

        if act[1] == "folds":
            return f"{act[0]}: folds "
        if act[1] == "checks":
            return f"{act[0]}: checks "
        if act[1] == "cashout":
            return f"{act[0]}: cashout "
        if act[1] == "calls":
            return "{}: calls {}{}{}".format(
                act[0],
                self.sym,
                act[2],
                " and is all-in" if act[3] else "",
            )
        if act[1] == "bets":
            return "{}: bets {}{}{}".format(
                act[0],
                self.sym,
                act[2],
                " and is all-in" if act[3] else "",
            )
        if act[1] == "raises":
            return "{}: raises {}{} to {}{}{}".format(
                act[0],
                self.sym,
                act[2],
                self.sym,
                act[3],
                " and is all-in" if act[5] else "",
            )
        if act[1] == "completes":
            return "{}: completes to {}{}{}".format(
                act[0],
                self.sym,
                act[2],
                " and is all-in" if act[3] else "",
            )
        if act[1] == "small blind":
            return "{}: posts small blind {}{}{}".format(
                act[0],
                self.sym,
                act[2],
                " and is all-in" if act[3] else "",
            )
        if act[1] == "big blind":
            return "{}: posts big blind {}{}{}".format(
                act[0],
                self.sym,
                act[2],
                " and is all-in" if act[3] else "",
            )
        if act[1] == "straddle":
            return "{}: posts straddle {}{}{}".format(
                act[0],
                self.sym,
                act[2],
                " and is all-in" if act[3] else "",
            )
        if act[1] == "button blind":
            return "{}: posts button blind {}{}{}".format(
                act[0],
                self.sym,
                act[2],
                " and is all-in" if act[3] else "",
            )
        if act[1] == "both":
            return "{}: posts small & big blinds {}{}{}".format(
                act[0],
                self.sym,
                act[2],
                " and is all-in" if act[3] else "",
            )
        if act[1] == "ante":
            return "{}: posts the ante {}{}{}".format(
                act[0],
                self.sym,
                act[2],
                " and is all-in" if act[3] else "",
            )
        if act[1] == "bringin":
            return "{}: brings in for {}{}{}".format(
                act[0],
                self.sym,
                act[2],
                " and is all-in" if act[3] else "",
            )
        if act[1] == "discards":
            return "{}: discards {} {}{}".format(
                act[0],
                act[2],
                "card" if act[2] == 1 else "cards",
                (" [" + " ".join(self.discards[street][act[0]]) + "]" if self.hero == act[0] else ""),
            )
        if act[1] == "stands pat":
            return f"{act[0]}: stands pat"
        return None

    def get_actions_short(self, player, street):
        """Returns a string with shortcuts for the actions of the given player and the given street
        F ... fold, X ... Check, B ...Bet, C ... Call, R ... Raise, CO ... CashOut.

        A street this game does not have has no actions on it, which is not an
        error: All-in or Fold has no preflop, and asking for one used to raise
        and cost the caller the whole hand rather than an empty column.
        """
        actions = self.actions.get(street, [])
        result = []
        for action in actions:
            if player in action:
                if action[1] == "folds":
                    result.append("F")
                elif action[1] == "checks":
                    result.append("X")
                elif action[1] == "bets":
                    result.append("B")
                elif action[1] == "calls":
                    result.append("C")
                elif action[1] == "raises":
                    result.append("R")
                elif action[1] == "cashout":
                    result.append("CO")
        return "".join(result)

    def get_actions_short_streets(self, player, *streets):
        """Returns a string with shortcuts for the actions of the given player on all given streets seperated by ','."""
        result = []
        for street in streets:
            action = self.get_actions_short(player, street)
            if len(action) > 0:  # if there is no action on later streets, nothing is added.
                result.append(action)
        return ",".join(result)

    def get_player_position(self, player):
        """Returns the given players postion (S, B, 0-7)."""
        # position has been added to the players list. It could be calculated from buttonpos and player seatnums,
        # but whats the point in calculating a value that has been there anyway?
        for p in self.players:
            if p[1] == player:
                return p[3]
        return None

    def getStakesAsString(self) -> str:
        """Return a string of the stakes of the current hand."""
        return f"{self.sym}{self.sb}/{self.sym}{self.bb}"

    def getStreetTotals(self):
        # tmp maps to street0..street4 pots plus the final pot (6 slots).
        tmp: list[Decimal | int] = [0, 0, 0, 0, 0, 0]
        i = 0
        for street in self.allStreets:
            if street == "BLINDSANTES":
                continue
            # Run-it-twice hands append duplicate board streets (FLOP1, TURN1,
            # RIVER1, FLOP2, ...) that carry no additional betting. Skip those
            # run-suffixed streets so the fixed 6-slot array cannot overflow;
            # base street names never end in a digit.
            if street[-1].isdigit():
                continue
            if i < 5:
                tmp[i] = self.pot.getTotalAtStreet(street)
                i += 1
        tmp[5] = sum(self.pot.committed.values()) + sum(self.pot.common.values())
        return tmp

    def writeGameLine(self):
        """Return the first HH line for the current hand."""
        gs = f"PokerStars Game #{self.handid}: "

        if self.tourNo is not None and self.mixed is not None:  # mixed tournament
            gs = (
                gs
                + f"Tournament #{self.tourNo}, {self.buyin} {self.MS[self.mixed]} ({self.getGameTypeAsString()}) - Level {self.level} ({self.getStakesAsString()}) - "
            )
        elif self.tourNo is not None:  # all other tournaments
            gs = (
                gs
                + f"Tournament #{self.tourNo}, {self.buyin} {self.getGameTypeAsString()} - Level {self.level} ({self.getStakesAsString()}) - "
            )
        elif self.mixed is not None:  # all other mixed games
            gs = gs + f" {self.MS[self.mixed]} ({self.getGameTypeAsString()}, {self.getStakesAsString()}) - "
        else:  # non-mixed cash games
            gs = gs + f" {self.getGameTypeAsString()} ({self.getStakesAsString()}) - "

        if not isinstance(self.startTime, datetime.datetime):
            log.error(
                "*** ERROR - HAND: calling writeGameLine with unexpected STARTTIME value. "
                f"Expecting datetime.date object, received: {self.startTime}",
            )
            log.error(
                "*** Make sure your HandHistoryConverter is setting hand.startTime properly!",
            )
            log.debug(f"*** Game String: {gs}")
            return gs
        timestr = datetime.datetime.strftime(self.startTime, "%Y/%m/%d %H:%M:%S ET")
        return gs + timestr

    def writeTableLine(self):
        table_string = "Table "
        if self.gametype["type"] == "tour":
            table_string = table_string + f"'{self.tourNo} {self.tablename}' {self.maxseats}-max"
        else:
            table_string = table_string + f"'{self.tablename}' {self.maxseats}-max"
        if self.gametype["currency"] == "play":
            table_string = table_string + " (Play Money)"
        if self.buttonpos is not None and self.buttonpos != 0:
            table_string = table_string + f" Seat #{self.buttonpos} is the button"
        return table_string

    @staticmethod
    def _output_stream(fh: TextIO | None) -> TextIO:
        """Return the requested text stream or the current redirected stdout."""
        return sys.stdout if fh is None else fh

    def writeHand(self, fh: TextIO | None = None) -> None:
        # Format PokerStars.
        fh = self._output_stream(fh)
        log.info(f"Writing game line: {self.writeGameLine()}")
        log.info(f"Writing table line: {self.writeTableLine()}")
        fh.write(f"{self.writeGameLine()}\n")
        fh.write(f"{self.writeTableLine()}\n")


class HoldemOmahaHand(Hand):
    @staticmethod
    def _is_community_street(street: str) -> bool:
        """Return whether *street* names a board street, including multi-run boards."""
        return any(
            street == base or (street.startswith(base) and street.removeprefix(base).isdigit())
            for base in ("FLOP", "TURN", "RIVER")
        )

    def __init__(
        self,
        config,
        hhc,
        sitename,
        gametype,
        handText,
        builtFrom="HHC",
        handid=None,
    ) -> None:
        self.config = config
        if gametype["base"] != "hold":
            pass  # or indeed don't pass and complain instead
        log.debug("HoldemOmahaHand")
        self.allStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        if gametype["category"] == "fusion":
            self.holeStreets = ["PREFLOP", "FLOP", "TURN"]
        else:
            self.holeStreets = ["PREFLOP"]
        if gametype["category"] == "irish":
            self.discardStreets = ["TURN"]
        else:
            self.discardStreets = ["PREFLOP"]
        self.communityStreets = ["FLOP", "TURN", "RIVER"]
        self.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        if gametype["category"] == "aof_omaha":
            self.allStreets = ["BLINDSANTES", "FLOP", "TURN", "RIVER"]
            self.holeStreets = ["FLOP"]
            self.communityStreets = ["FLOP", "TURN", "RIVER"]
            self.actionStreets = ["BLINDSANTES", "FLOP", "TURN", "RIVER"]
        if gametype["category"] == "aof_holdem":
            self.allStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
            self.holeStreets = ["PREFLOP"]
            self.communityStreets = ["FLOP", "TURN", "RIVER"]
            self.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]

        # Initialize the base Hand class
        Hand.__init__(self, self.config, sitename, gametype, handText, builtFrom="HHC")

        # Initialize specific attributes for HoldemOmahaHand
        self.sb = gametype["sb"]
        self.bb = gametype["bb"]
        self.committed: dict[str, Decimal] = {}

        if hasattr(hhc, "in_path"):
            self.in_path = hhc.in_path
        else:
            self.in_path = "database"

        # Populate a HoldemOmahaHand
        # Generally, we call 'read' methods here, which get the info according to the particular filter (hhc)
        # which then invokes a 'addXXX' callback
        if builtFrom == "HHC":
            hhc.readHandInfo(self)
            if self.gametype["type"] == "tour":
                self.tablename = f"{self.tourNo} {self.tablename}"
            hhc.readPlayerStacks(self)
            hhc.compilePlayerRegexs(self)
            hhc.markStreets(self)

            if self.cancelled:
                return

            hhc.readBlinds(self)
            hhc.readSTP(self)
            hhc.readAntes(self)
            hhc.readButton(self)
            hhc.readHoleCards(self)
            hhc.readShowdownActions(self)
            # Read actions in street order
            for street, text in list(self.streets.items()):
                if text and self._is_community_street(street):
                    hhc.readCommunityCards(self, street)

            # Update actionStreets if runItTimes was set during readCommunityCards
            if self.runItTimes >= 2:
                run_it_streets = []
                for run in range(1, self.runItTimes + 1):
                    run_it_streets += [f"FLOP{run}", f"TURN{run}", f"RIVER{run}"]
                for street in run_it_streets:
                    if street not in self.actionStreets:
                        self.actionStreets.append(street)
                        self.bets.setdefault(street, {})
                        self.lastBet.setdefault(street, 0)
                        self.actions.setdefault(street, [])
                        # Do NOT clobber community cards already read for this run.
                        self.board.setdefault(street, [])
                        # Add existing players to new street
                        for player_info in self.players:
                            player_name = player_info[1]  # player name is at index 1
                            self.bets[street].setdefault(player_name, [])
                    # Also add to allStreets and streets if not present
                    if street not in self.allStreets:
                        self.allStreets.append(street)
                    if street not in self.streets:
                        self.streets[street] = ""

            for street in self.actionStreets:
                if self.streets[street] or gametype["split"]:
                    hhc.readAction(self, street)
                    self.pot.markTotal(street)
            hhc.readCollectPot(self)
            hhc.readShownCards(self)
            # readOther is used by some converters like Bovada for special handling before totalPot
            hhc.readOther(self)
            self.pot.handid = self.handid  # This is only required so Pot can throw it in totalPot
            self.totalPot()  # Finalize it (total the pot)
            log.debug(f"self.totalpot {self.totalpot}")
            log.debug(f" type self.totalpot {type(self.totalpot)}")
            if self.gametype["type"] == "ring":
                log.debug("Ring case")
                log.debug(f"self.rake {self.rake}")
                log.debug(f"type self.rake {type(self.rake)}")
                if self.rake is None:
                    log.warning("self.rake is None")
                    hhc.getRake(self)
            else:
                self.rake = 0
            if self.maxseats is None:
                self.maxseats = hhc.guessMaxSeats(self)
            self.sittingOut()
            hhc.readTourneyResults(self)
            # readOther moved earlier before totalPot() for Bovada handling
        elif builtFrom == "DB":
            # Creator expected to call hhc.select(hid) to fill out object
            log.debug("HoldemOmaha hand initialised for select()")
            self.maxseats = 10
        elif builtFrom == "HTTP_CAPTURE":
            # The room adapter fills players, actions, pots and results after
            # construction through execute_hand_operations().
            log.debug("HoldemOmaha hand initialised from HTTP capture")
        else:
            log.warning("Neither HHC nor DB+handID provided")

    def addShownCards(
        self,
        cards,
        player,
        shown=True,
        mucked=False,
        dealt=False,
        string=None,
    ) -> None:
        if player == self.hero:  # we have hero's cards just update shown/mucked
            if shown:
                self.shown.add(player)
            if mucked:
                self.mucked.add(player)
        elif is_aof_category(self.gametype["category"]):
            self.addHoleCards(
                "FLOP",
                player,
                open=[],
                closed=cards,
                shown=shown,
                mucked=mucked,
                dealt=dealt,
            )
        elif len(cards) in (2, 3, 4, 6) or self.gametype["category"] in (
            "5_omahahi",
            "5_omaha8",
            "cour_hi",
            "cour_hilo",
            "fusion",
        ):  # avoid adding board by mistake (Everleaf problem)
            self.addHoleCards(
                "PREFLOP",
                player,
                open=[],
                closed=cards,
                shown=shown,
                mucked=mucked,
                dealt=dealt,
            )

        elif len(cards) == 5:  # cards holds a winning hand, not hole cards
            # The history printed the exact 5-card winning combination: keep it
            # so the replayer can highlight those cards at showdown.
            self.winningHand[player] = list(cards)
            # filter( lambda x: x not in b, a )             # calcs a - b where a and b are lists
            # so diff is set to the winning hand minus the board cards, if we're lucky that leaves the hole cards
            diff = [x for x in cards if x not in self.board["FLOP"] + self.board["TURN"] + self.board["RIVER"]]
            if len(diff) == 2 and self.gametype["category"] in ("holdem"):
                self.addHoleCards(
                    "PREFLOP",
                    player,
                    open=[],
                    closed=diff,
                    shown=shown,
                    mucked=mucked,
                    dealt=dealt,
                )
        if string is not None:
            self.showdownStrings[player] = string

    def join_holecards(self, player, asList=False):
        holeNo = Card.games[self.gametype["category"]][5][0][1]
        hcs = ["0x"] * holeNo
        if self.gametype["category"] == "fusion":
            for street in self.holeStreets:
                if player in list(self.holecards[street].keys()):
                    if street == "PREFLOP":
                        if len(self.holecards[street][player][1]) == 1:
                            continue
                        for i in 0, 1:
                            hcs[i] = self.holecards[street][player][1][i]
                            hcs[i] = hcs[i][0:1].upper() + hcs[i][1:2]
                        try:
                            for i in range(2, holeNo):
                                hcs[i] = self.holecards[street][player][1][i]
                                hcs[i] = hcs[i][0:1].upper() + hcs[i][1:2]
                        except IndexError:
                            log.debug("Why did we get an indexerror?")
                    elif street == "FLOP":
                        if len(self.holecards[street][player][1]) == 1:
                            continue
                        hcs[2] = self.holecards[street][player][0][0]
                        hcs[2] = hcs[2][0:1].upper() + hcs[2][1:2]
                    elif street == "TURN":
                        if len(self.holecards[street][player][1]) == 1:
                            continue
                        hcs[3] = self.holecards[street][player][0][0]
                        hcs[3] = hcs[3][0:1].upper() + hcs[3][1:2]

        else:
            for street in self.holeStreets:
                if player in list(self.holecards[street].keys()):
                    if len(self.holecards[street][player][1]) == 1:
                        continue
                    for i in 0, 1:
                        hcs[i] = self.holecards[street][player][1][i]
                        hcs[i] = hcs[i][0:1].upper() + hcs[i][1:2]
                    try:
                        for i in range(2, holeNo):
                            hcs[i] = self.holecards[street][player][1][i]
                            hcs[i] = hcs[i][0:1].upper() + hcs[i][1:2]
                    except IndexError:
                        log.debug("Why did we get an indexerror?")

        if asList:
            return hcs
        return " ".join(hcs)

    def _write_showdown(self, fh) -> None:
        """Write complete shown hands and mucked players in seat order."""
        lines = []
        for player_data in self.players:
            player = player_data[1]
            if player in self.shown:
                cards = self.join_holecards(player, asList=True)
                if "0x" in cards:
                    continue
                description = self.showdownStrings.get(player, "")
                suffix = f" ({description})" if description else ""
                lines.append(f"{player}: shows [{' '.join(cards)}]{suffix}\n")
            elif player in self.mucked:
                lines.append(f"{player}: mucks hand\n")

        if lines:
            fh.write("*** SHOW DOWN ***\n")
            fh.writelines(lines)

    def writeHand(self, fh: TextIO | None = None) -> None:
        # PokerStars format.
        fh = self._output_stream(fh)
        super().writeHand(fh)

        hole_street = self.holeStreets[0] if self.holeStreets else "PREFLOP"
        # First non-blind street with actions (the decision street in AoF).
        initial_street = "FLOP"
        for s in (getattr(self, "actionStreets", []) or []):
            if s != "BLINDSANTES" and self.actions.get(s):
                initial_street = s
                break

        players_who_act_preflop = set(
            ([x[0] for x in self.actions[initial_street]] + [x[0] for x in self.actions["BLINDSANTES"]]),
        )
        log.debug(self.actions[initial_street])
        for player in [x for x in self.players if x[1] in players_who_act_preflop]:
            # Only displays the stacks of players who acted preflop.
            log.info(
                f"Seat {player[0]}: {player[1]} (${float(player[2]):.2f} in chips)",
            )

        if self.actions["BLINDSANTES"]:
            log.debug(f"BLINDSANTES actions: {self.actions['BLINDSANTES']}")
            for act in self.actions["BLINDSANTES"]:
                fh.write(f"{self.actionString(act)}\n")

        fh.write("*** HOLE CARDS ***\n")
        for player in self.dealt:
            fh.write(
                f"Dealt to {player} [{' '.join(self.holecards[hole_street][player][1])}]\n",
            )

        if self.hero == "":
            for player in self.shown.difference(self.dealt):
                fh.write(
                    f"Dealt to {player} [{' '.join(self.holecards[hole_street][player][1])}]\n",
                )

        if self.actions[initial_street]:
            for act in self.actions[initial_street]:
                fh.write(f"{self.actionString(act)}\n")

        if self.board["FLOP"]:
            fh.write(f"*** FLOP *** [{' '.join(self.board['FLOP'])}]\n")
        if self.actions["FLOP"]:
            for act in self.actions["FLOP"]:
                fh.write(f"{self.actionString(act)}\n")

        if self.board["TURN"]:
            fh.write(
                f"*** TURN *** [{' '.join(self.board['FLOP'])}] [{' '.join(self.board['TURN'])}]\n",
            )
        if self.actions["TURN"]:
            for act in self.actions["TURN"]:
                fh.write(f"{self.actionString(act)}\n")

        if self.board["RIVER"]:
            fh.write(
                f"*** RIVER *** [{' '.join(self.board['FLOP'] + self.board['TURN'])}] [{' '.join(self.board['RIVER'])}]\n",
            )
        if self.actions["RIVER"]:
            for act in self.actions["RIVER"]:
                fh.write(f"{self.actionString(act)}\n")

        self._write_showdown(fh)

        # Current PS format has the lines:
        # Uncalled bet ($111.25) returned to s0rrow
        # s0rrow collected $5.15 from side pot
        # stervels: shows [Ks Qs] (two pair, Kings and Queens)
        # stervels collected $45.35 from main pot
        # Immediately before the summary.
        # The current importer uses those lines for importing winning rather than the summary
        for name in self.pot.returned:
            fh.write(
                f"Uncalled bet ({self.sym}{self.pot.returned[name]}) returned to {name}\n",
            )

        for entry in self.collected:
            fh.write(f"{entry[0]} collected {self.sym}{entry[1]} from pot\n")

        fh.write("*** SUMMARY ***\n")
        fh.write(f"{self.pot} | Rake {self.sym}{self.rake:.2f}\n")

        board = []
        for street in ["FLOP", "TURN", "RIVER"]:
            board += self.board[street]
        if board:  # sometimes hand ends preflop without a board
            fh.write(f"Board [{' '.join(board)}]\n")

        for player in [x for x in self.players if x[1] in players_who_act_preflop]:
            seatnum = player[0]
            name = player[1]
            cards = self.holecards.get(hole_street, {}).get(name, [None, []])[1]
            cards_str = f" [{' '.join(cards)}]" if cards else ""
            if name in self.collectees and name in self.shown:
                fh.write(
                    f"Seat {seatnum}: {name} showed{cards_str} "
                    f"and won ({self.sym}{self.collectees[name]})\n",
                )
            elif name in self.collectees:
                fh.write(
                    f"Seat {seatnum}: {name} collected ({self.sym}{self.collectees[name]})\n",
                )
            elif name in self.folded:
                fh.write(f"Seat {seatnum}: {name} folded\n")
            elif name in self.shown:
                fh.write(
                    f"Seat {seatnum}: {name} showed{cards_str} "
                    f"and lost with...\n",
                )
            elif name in self.mucked:
                fh.write(
                    f"Seat {seatnum}: {name} mucked{cards_str}\n",
                )
            else:
                fh.write(f"Seat {seatnum}: {name} mucked\n")

        fh.write("\n\n")


class DrawHand(Hand):
    def __init__(
        self,
        config,
        hhc,
        sitename,
        gametype,
        handText,
        builtFrom="HHC",
        handid=None,
    ) -> None:
        self.config = config
        if gametype["base"] != "draw":
            pass  # or indeed don't pass and complain instead
        self.streetList = ["BLINDSANTES", "DEAL", "DRAWONE"]
        self.allStreets = ["BLINDSANTES", "DEAL", "DRAWONE"]
        self.holeStreets = ["DEAL", "DRAWONE"]
        self.actionStreets = ["BLINDSANTES", "DEAL", "DRAWONE"]
        if gametype["category"] in [
            "27_3draw",
            "badugi",
            "a5_3draw",
            "badacey",
            "badeucey",
            "drawmaha",
        ]:
            self.streetList += ["DRAWTWO", "DRAWTHREE"]
            self.allStreets += ["DRAWTWO", "DRAWTHREE"]
            self.holeStreets += ["DRAWTWO", "DRAWTHREE"]
            self.actionStreets += ["DRAWTWO", "DRAWTHREE"]
        self.discardStreets = self.holeStreets
        self.communityStreets = []
        Hand.__init__(self, self.config, sitename, gametype, handText)
        self.sb = gametype["sb"]
        self.bb = gametype["bb"]
        if hasattr(hhc, "in_path"):
            self.in_path = hhc.in_path
        else:
            self.in_path = "database"
        # Populate the draw hand.
        if builtFrom == "HHC":
            hhc.readHandInfo(self)
            if self.gametype["type"] == "tour":
                self.tablename = f"{self.tourNo} {self.tablename}"
            hhc.readPlayerStacks(self)
            hhc.compilePlayerRegexs(self)
            hhc.markStreets(self)
            # markStreets in Draw may match without dealing cards
            if self.streets["DEAL"] is None:
                log.error(
                    f"Street 'DEAL' is empty. Was hand '{self.handid}' cancelled?",
                )
                raise FpdbParseError
            hhc.readBlinds(self)
            hhc.readSTP(self)
            hhc.readAntes(self)
            hhc.readButton(self)
            hhc.readHoleCards(self)
            # Read actions in street order
            for street in self.streetList:
                if self.streets[street]:
                    hhc.readAction(self, street)
                    self.pot.markTotal(street)
            # readShowdownActions must run AFTER readAction so that addShownCards
            # can resolve the correct target street (the last draw round). Running it
            # before would leave the action streets empty, causing addShownCards to
            # fall back to DEAL and clobber the hero's original dealt cards — which
            # made the replayer show an incomplete starting hand for draw games.
            hhc.readShowdownActions(self)
            hhc.readCollectPot(self)
            hhc.readShownCards(self)
            # readOther is used by some converters like Bovada for special handling before totalPot
            hhc.readOther(self)
            self.pot.handid = self.handid  # This is only required so Pot can throw it in totalPot
            self.totalPot()  # finalise it (total the pot)
            hhc.getRake(self)
            if self.maxseats is None:
                self.maxseats = hhc.guessMaxSeats(self)
            self.sittingOut()
            hhc.readTourneyResults(self)
            # readOther moved earlier before totalPot() for Bovada handling

        elif builtFrom == "DB":
            # Creator expected to call hhc.select(hid) to fill out object
            self.maxseats = 10

    def addShownCards(
        self,
        cards,
        player,
        shown=True,
        mucked=False,
        dealt=False,
        string=None,
    ) -> None:
        # if player == self.hero: # we have hero's cards just update shown/mucked
        #    if shown:  self.shown.add(player)
        #    if mucked: self.mucked.add(player)
        # else:
        #    pass
        # Find the last street with action and add the hole cards to that street
        target_street = self.actionStreets[-1]
        for street in reversed(self.actionStreets):
            if self.actions.get(street):
                target_street = street
                break

        if target_street == "BLINDSANTES":
            target_street = "DEAL"

        self.addHoleCards(
            target_street,
            player,
            open=[],
            closed=cards,
            shown=shown,
            mucked=mucked,
            dealt=dealt,
        )
        if string is not None:
            self.showdownStrings[player] = string

    def holecardsAsSet(self, street, player):
        """Return holdcards: (oc, nc) as set()."""
        (nc, oc) = self.holecards[street][player]
        nc = set(nc)
        oc = set(oc)
        return (nc, oc)

    def join_holecards(self, player, asList=False, street=False):
        """With asList = True it returns the set cards for a player including down cards if they aren't know."""
        handsize = Card.games[self.gametype["category"]][5][0][1]
        holecards = ["0x"] * 20

        for i, _street in enumerate(self.holeStreets):
            if player in list(self.holecards[_street].keys()):
                allhole = self.holecards[_street][player][1] + self.holecards[_street][player][0]
                allhole = allhole[:handsize]
                for c in range(len(allhole)):
                    idx = c + i * 5
                    holecards[idx] = allhole[c]

        result = []
        if street is False:
            result = holecards
        elif street in self.holeStreets:
            # Each draw street occupies a 5-slot block, but only `handsize` cards
            # belong to it (e.g. badugi holds 4). Slice by handsize so games with
            # fewer than 5 cards don't expose a trailing "0x" placeholder.
            base = self.holeStreets.index(street) * 5
            result = holecards[base : base + handsize]
        return result if asList else " ".join(result)

    def _write_showdown(self, fh) -> None:
        """Write known draw showdown cards in stable seat order."""
        if not self.shown and not self.mucked:
            return
        fh.write("*** SHOW DOWN ***\n")
        for player in (seat[1] for seat in self.players):
            if player in self.shown:
                final_street = next(
                    (street for street in reversed(self.holeStreets) if player in self.holecards[street]),
                    None,
                )
                if final_street is None:
                    continue
                cards = self.join_holecards(player, street=final_street)
                description = self.showdownStrings.get(player, "")
                suffix = f" ({description})" if description else ""
                fh.write(f"{player}: shows [{cards}]{suffix}\n")
            elif player in self.mucked:
                fh.write(f"{player}: mucks hand\n")

    def writeHand(self, fh: TextIO | None = None) -> None:
        # PokerStars format.
        # HH output should not be translated
        fh = self._output_stream(fh)
        super().writeHand(fh)

        players_who_act_ondeal = set(
            [x[0] for x in self.actions["DEAL"]] + [x[0] for x in self.actions["BLINDSANTES"]],
        )

        for player in [x for x in self.players if x[1] in players_who_act_ondeal]:
            # Only print stacks of players who do something on deal
            fh.write(
                f"Seat {player[0]}: {player[1]} ({self.sym}{player[2]} in chips)\n",
            )

        if "BLINDSANTES" in self.actions:
            for act in self.actions["BLINDSANTES"]:
                fh.write(f"{act[0]}: {act[1]} {act[2]} {self.sym}{act[3]}\n")

        if "DEAL" in self.actions:
            fh.write("*** DEALING HANDS ***\n")
            for player in [x[1] for x in self.players if x[1] in players_who_act_ondeal]:
                if "DEAL" in self.holecards and player in self.holecards["DEAL"]:
                    nc = self.holecards["DEAL"][player][0]
                    fh.write(f"Dealt to {player}: [{' '.join(nc)}]\n")
            for act in self.actions["DEAL"]:
                fh.write(f"{self.actionString(act, 'DEAL')}\n")

        if "DRAWONE" in self.actions:
            fh.write("*** FIRST DRAW ***\n")
            for act in self.actions["DRAWONE"]:
                fh.write(f"{self.actionString(act, 'DRAWONE')}\n")
                if act[0] == self.hero and act[1] == "discards":
                    nc, oc = self.holecardsAsSet("DRAWONE", act[0])
                    dc = self.discards["DRAWONE"][act[0]]
                    kc = oc - dc
                    fh.write(f"Dealt to {act[0]} [{' '.join(kc)}] [{' '.join(nc)}]\n")

        if "DRAWTWO" in self.actions:
            fh.write("*** SECOND DRAW ***\n")
            for act in self.actions["DRAWTWO"]:
                fh.write(f"{self.actionString(act, 'DRAWTWO')}\n")
                if act[0] == self.hero and act[1] == "discards":
                    nc, oc = self.holecardsAsSet("DRAWTWO", act[0])
                    dc = self.discards["DRAWTWO"][act[0]]
                    kc = oc - dc
                    fh.write(f"Dealt to {act[0]} [{' '.join(kc)}] [{' '.join(nc)}]\n")

        if "DRAWTHREE" in self.actions:
            fh.write("*** THIRD DRAW ***\n")
            for act in self.actions["DRAWTHREE"]:
                fh.write(f"{self.actionString(act, 'DRAWTHREE')}\n")
                if act[0] == self.hero and act[1] == "discards":
                    nc, oc = self.holecardsAsSet("DRAWTHREE", act[0])
                    dc = self.discards["DRAWTHREE"][act[0]]
                    kc = oc - dc
                    fh.write(f"Dealt to {act[0]} [{' '.join(kc)}] [{' '.join(nc)}]\n")

        self._write_showdown(fh)

        for name in self.pot.returned:
            fh.write(
                f"Uncalled bet ({self.sym}{self.pot.returned[name]}) returned to {name}\n",
            )
        for entry in self.collected:
            fh.write(f"{entry[0]} collected {self.sym}{entry[1]} from pot\n")

        fh.write("*** SUMMARY ***\n")
        fh.write(f"{self.pot} | Rake {self.sym}{self.rake:.2f}\n")
        fh.write("\n\n")


class StudHand(Hand):
    def __init__(
        self,
        config,
        hhc,
        sitename,
        gametype,
        handText,
        builtFrom="HHC",
        handid=None,
    ) -> None:
        self.config = config
        if gametype["base"] != "stud":
            pass  # or indeed don't pass and complain instead

        self.communityStreets = []
        if gametype["category"] == "5_studhi":
            self.allStreets = ["BLINDSANTES", "SECOND", "THIRD", "FOURTH", "FIFTH"]
            self.actionStreets = ["BLINDSANTES", "SECOND", "THIRD", "FOURTH", "FIFTH"]
            self.streetList = [
                "BLINDSANTES",
                "SECOND",
                "THIRD",
                "FOURTH",
                "FIFTH",
            ]  # a list of the observed street names in order
            self.holeStreets = ["SECOND", "THIRD", "FOURTH", "FIFTH"]
        else:
            self.allStreets = [
                "BLINDSANTES",
                "THIRD",
                "FOURTH",
                "FIFTH",
                "SIXTH",
                "SEVENTH",
            ]
            self.actionStreets = [
                "BLINDSANTES",
                "THIRD",
                "FOURTH",
                "FIFTH",
                "SIXTH",
                "SEVENTH",
            ]
            self.streetList = [
                "BLINDSANTES",
                "THIRD",
                "FOURTH",
                "FIFTH",
                "SIXTH",
                "SEVENTH",
            ]  # a list of the observed street names in order
            self.holeStreets = ["THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
        self.discardStreets = self.holeStreets
        Hand.__init__(self, self.config, sitename, gametype, handText)
        self.sb = gametype["sb"]
        self.bb = gametype["bb"]
        if hasattr(hhc, "in_path"):
            self.in_path = hhc.in_path
        else:
            self.in_path = "database"
        # Populate the StudHand
        # Generally, we call a 'read' method here, which gets the info according to the particular filter (hhc)
        # which then invokes a 'addXXX' callback
        if builtFrom == "HHC":
            hhc.readHandInfo(self)
            if self.gametype["type"] == "tour":
                self.tablename = f"{self.tourNo} {self.tablename}"
            hhc.readPlayerStacks(self)
            hhc.compilePlayerRegexs(self)
            hhc.markStreets(self)
            hhc.readSTP(self)
            hhc.readAntes(self)
            hhc.readBringIn(self)
            hhc.readHoleCards(self)
            hhc.readShowdownActions(self)
            # Read actions in street order
            for street in self.actionStreets:
                if street == "BLINDSANTES":
                    continue  # OMG--sometime someone folds in the ante round
                if self.streets[street]:
                    log.debug(f"{street}{self.streets[street]}")
                    hhc.readAction(self, street)
                    self.pot.markTotal(street)
            hhc.readCollectPot(self)
            hhc.readShownCards(self)  # not done yet
            # readOther is used by some converters like Bovada for special handling before totalPot
            hhc.readOther(self)
            self.pot.handid = self.handid  # This is only required so Pot can throw it in totalPot
            self.totalPot()  # finalise it (total the pot)
            hhc.getRake(self)
            if self.maxseats is None:
                self.maxseats = hhc.guessMaxSeats(self)
            self.sittingOut()
            hhc.readTourneyResults(self)
            # readOther moved earlier before totalPot() for Bovada handling

        elif builtFrom == "DB":
            # Creator expected to call hhc.select(hid) to fill out object
            self.maxseats = 10

    def addShownCards(
        self,
        cards,
        player,
        shown=True,
        mucked=False,
        dealt=False,
        string=None,
    ) -> None:
        if player == self.hero:  # we have hero's cards just update shown/mucked
            if shown:
                self.shown.add(player)
            if mucked:
                self.mucked.add(player)
        else:
            if self.gametype["category"] == "5_studhi" and len(cards) > 4:
                self.addHoleCards(
                    "SECOND",
                    player,
                    open=[cards[1]],
                    closed=[cards[0]],
                    shown=shown,
                    mucked=mucked,
                )
                self.addHoleCards(
                    "THIRD",
                    player,
                    open=[cards[2]],
                    closed=[cards[1]],
                    shown=shown,
                    mucked=mucked,
                )
                self.addHoleCards(
                    "FOURTH",
                    player,
                    open=[cards[3]],
                    closed=cards[1:2],
                    shown=shown,
                    mucked=mucked,
                )
                self.addHoleCards(
                    "FIFTH",
                    player,
                    open=[cards[4]],
                    closed=cards[1:3],
                    shown=shown,
                    mucked=mucked,
                )
            # Six cards is enough to place a seven-stud hand: they are the two
            # down cards followed by the four up cards, and the seventh-street
            # card is only added when the room actually lists it. Requiring all
            # seven silently dropped every showdown from rooms that print six
            # (ACR shows "[7h 6s 8h 4c 5c 5s]" and leaves the last card to the
            # deal line). The player's down cards were then never recorded, so
            # join_holecards handed back his up cards twice over -- an
            # impossible hand that made the hi/lo evaluation fail, leaving
            # assembleHandsPots with no pot rows to write after it had already
            # zeroed the rake.
            if len(cards) > 5:
                self.addHoleCards(
                    "THIRD",
                    player,
                    open=[cards[2]],
                    closed=cards[0:2],
                    shown=shown,
                    mucked=mucked,
                )
                self.addHoleCards(
                    "FOURTH",
                    player,
                    open=[cards[3]],
                    closed=[cards[2]],
                    shown=shown,
                    mucked=mucked,
                )
                self.addHoleCards(
                    "FIFTH",
                    player,
                    open=[cards[4]],
                    closed=cards[2:4],
                    shown=shown,
                    mucked=mucked,
                )
                self.addHoleCards(
                    "SIXTH",
                    player,
                    open=[cards[5]],
                    closed=cards[2:5],
                    shown=shown,
                    mucked=mucked,
                )
                if len(cards) > 6:
                    self.addHoleCards(
                        "SEVENTH",
                        player,
                        open=[],
                        closed=[cards[6]],
                        shown=shown,
                        mucked=mucked,
                    )
                else:
                    # Six cards listed: the seventh is only in the deal line,
                    # which recorded it as an up card. join_holecards reads a
                    # non-hero's seventh street from the *closed* slot, where the
                    # deal line leaves its running list of earlier up cards --
                    # returning them a second time and building an impossible
                    # hand. Keep just the seventh card, in the slot that is read.
                    # Idempotent: this runs once from readShowdownActions and
                    # again from readShownCards. The deal line leaves the card
                    # open with the earlier up cards closed beside it; once
                    # normalised the closed slot holds that single card, and a
                    # second pass must keep it rather than clear it.
                    seventh = self.holecards.get("SEVENTH", {}).get(player)
                    last_card = None
                    if seventh:
                        if seventh[0]:
                            last_card = seventh[0][0]
                        elif len(seventh[1]) == 1:
                            last_card = seventh[1][0]
                    self.addHoleCards(
                        "SEVENTH",
                        player,
                        open=[],
                        closed=[last_card] if last_card else [],
                        shown=shown,
                        mucked=mucked,
                    )
        if string is not None:
            self.showdownStrings[player] = string

    def addPlayerCards(self, player, street, open=None, closed=None) -> None:
        """Assigns observed cards to a player.
        player  (string) name of player
        street  (string) the street name (in streetList)
        open  list of card bigrams e.g. ['2h','Jc'], dealt face up
        closed    likewise, but known only to player.
        """
        if closed is None:
            closed = []
        if open is None:
            open = []
        log.debug(f"addPlayerCards {player}, o{open} x{closed}")
        self.checkPlayerExists(player, "addPlayerCards")
        self.holecards[street][player] = (open, closed)

    def addComplete(self, street, player, amountTo) -> None:
        """Add a stud completion on *street* by *player* to *amountTo*."""
        log.debug(f"{street} {player} completes {amountTo}")
        amountTo = amountTo.replace(",", "")  # some sites have commas
        self.checkPlayerExists(player, "addComplete")
        Bp = self.lastBet[street]
        Bc = sum(self.bets[street][player])
        Rt = Decimal(amountTo)
        C = Bp - Bc
        Rb = Rt - C - Bc
        self._addRaise(street, player, C, Rb, Rt, "completes")

    def addBringIn(self, player, bringin) -> None:
        if player is not None:
            street = "SECOND" if self.gametype["category"] == "5_studhi" else "THIRD"
            log.debug(f"Bringin: {player}, {bringin}")
            bringin = bringin.replace(",", "")  # some sites have commas
            self.checkPlayerExists(player, "addBringIn")
            bringin = Decimal(bringin)
            self.bets[street][player].append(bringin)
            self.stacks[player] -= bringin
            act = (player, "bringin", bringin, self.stacks[player] == 0)
            self.actions[street].append(act)
            self.lastBet[street] = bringin
            self.pot.addMoney(player, bringin)

    def writeHand(self, fh: TextIO | None = None) -> None:
        # PokerStars format.
        # HH output should not be translated
        fh = self._output_stream(fh)
        super().writeHand(fh)

        players_who_post_antes = {x[0] for x in self.actions["BLINDSANTES"]}

        for player in [x for x in self.players if x[1] in players_who_post_antes]:
            # Only print stacks of players who post antes
            fh.write(
                f"Seat {player[0]}: {player[1]} ({self.sym}{player[2]} in chips)\n",
            )

        if "BLINDSANTES" in self.actions:
            for act in self.actions["BLINDSANTES"]:
                fh.write(f"{act[0]}: posts the ante {self.sym}{act[3]}\n")

        def write_street(street, label) -> None:
            if street in self.actions:
                dealt = 0
                for player in [x[1] for x in self.players if x[1] in players_who_post_antes]:
                    if player in self.holecards[street]:
                        dealt += 1
                        if dealt == 1:
                            fh.write(f"*** {label} ***\n")
                        fh.write(f"{self.writeHoleCards(street, player)}\n")
                for act in self.actions[street]:
                    fh.write(f"{self.actionString(act)}\n")

        write_street("THIRD", "3RD STREET")
        write_street("FOURTH", "4TH STREET")
        write_street("FIFTH", "5TH STREET")
        write_street("SIXTH", "6TH STREET")

        if "SEVENTH" in self.actions:
            fh.write("*** RIVER ***\n")
            for player in [x[1] for x in self.players if x[1] in players_who_post_antes]:
                if player in self.holecards["SEVENTH"]:
                    cards = self.writeHoleCards("SEVENTH", player)
                    if cards:
                        fh.write(f"{cards}\n")
            for act in self.actions["SEVENTH"]:
                fh.write(f"{self.actionString(act)}\n")

        if self.shown or self.mucked:
            fh.write("*** SHOW DOWN ***\n")
            for player in [x[1] for x in self.players]:
                if player in self.shown:
                    cards = self.join_holecards(player)
                    desc = self.showdownStrings.get(player, "")
                    if desc:
                        desc = f" ({desc})"
                    fh.write(f"{player}: shows [{cards}]{desc}\n")
                elif player in self.mucked:
                    fh.write(f"{player}: mucks hand\n")

        for name in self.pot.returned:
            fh.write(
                f"Uncalled bet ({self.sym}{self.pot.returned[name]}) returned to {name}\n",
            )
        for entry in self.collected:
            fh.write(f"{entry[0]} collected {self.sym}{entry[1]} from pot\n")

        fh.write("*** SUMMARY ***\n")
        # Explicitly format pot string to ensure side pots are written
        pot_str = f"Total pot {self.sym}{self.totalpot:.2f}"
        if self.pot.pots and len(self.pot.pots) > 0:
            pot_str += f" Main pot {self.sym}{self.pot.pots[0][0]:.2f}."
            if len(self.pot.pots) > 1:
                pot_str += "".join(
                    [f" Side pot {self.sym}{self.pot.pots[x][0]:.2f}." for x in range(1, len(self.pot.pots))]
                )

        fh.write(f"{pot_str} | Rake {self.sym}{self.rake:.2f}\n")

        board = [card for cards in self.board.values() for card in cards]
        if board:  # sometimes hand ends preflop without a board
            fh.write(f"Board [{' '.join(board)}]\n")

        for player in [x for x in self.players if x[1] in players_who_post_antes]:
            seatnum = player[0]
            name = player[1]
            if name in self.collectees and name in self.shown:
                fh.write(
                    f"Seat {seatnum}: {name} showed [{self.join_holecards(name)}] and won ({self.sym}{self.collectees[name]})\n",
                )
            elif name in self.collectees:
                fh.write(
                    f"Seat {seatnum}: {name} collected ({self.sym}{self.collectees[name]})\n",
                )
            elif name in self.shown:
                fh.write(
                    f"Seat {seatnum}: {name} showed [{self.join_holecards(name)}]\n",
                )
            elif name in self.mucked:
                fh.write(
                    f"Seat {seatnum}: {name} mucked [{self.join_holecards(name)}]\n",
                )
            elif name in self.folded:
                fh.write(f"Seat {seatnum}: {name} folded\n")
            else:
                fh.write(f"Seat {seatnum}: {name} mucked\n")

        fh.write("\n\n")

    def writeHoleCards(self, street, player):
        hc = f"Dealt to {player} ["
        if street == "THIRD":
            if player == self.hero:
                return (
                    hc
                    + " ".join(self.holecards[street][player][1])
                    + " "
                    + " ".join(self.holecards[street][player][0])
                    + "]"
                )
            return hc + " ".join(self.holecards[street][player][0]) + "]"

        if street == "SEVENTH" and player != self.hero:
            return None  # only write 7th st line for hero, LDO
        return (
            hc + " ".join(self.holecards[street][player][1]) + "] [" + " ".join(self.holecards[street][player][0]) + "]"
        )

    def join_holecards(self, player, asList=False):
        """Function returns a string for the stud writeHand method by default
        With asList = True it returns the set cards for a player including down cards if they aren't know.
        """
        holecards: list[str] = []
        for street in self.holeStreets:
            if player in self.holecards[street]:
                if (self.gametype["category"] == "5_studhi" and street == "SECOND") or (
                    self.gametype["category"] != "5_studhi" and street == "THIRD"
                ):
                    holecards = holecards + self.holecards[street][player][1] + self.holecards[street][player][0]
                elif street == "SEVENTH":
                    if player == self.hero:
                        holecards = holecards + self.holecards[street][player][0]
                    else:
                        holecards = holecards + self.holecards[street][player][1]
                else:
                    holecards = holecards + self.holecards[street][player][0]

        if asList:
            if self.gametype["category"] == "5_studhi":
                if len(holecards) < 2:
                    holecards = ["0x", *holecards]
                return holecards
            if player == self.hero:
                if len(holecards) < 3:
                    holecards = ["0x", "0x", *holecards]
                else:
                    return holecards
            elif len(holecards) == 7:
                return holecards
            elif len(holecards) <= 4:
                # Non hero folded before showdown, add first two downcards
                holecards = ["0x", "0x", *holecards]
            else:
                log.warning(
                    f"join_holecards: # of holecards should be either < 4, 4 or 7 - 5 and 6 should be impossible for anyone who is not a hero\njoin_holecards: holecards({player}): {holecards}",
                )
            if holecards == ["0x", "0x"]:
                log.warning(
                    f"join_holecards: Player '{player}' appears not to have been dealt a card",
                )
                # If a player is listed but not dealt a card in a cash game this can occur
                # Noticed in FTP Razz hand. Return 3 empty cards in this case
                holecards = ["0x", "0x", "0x"]
            return holecards
        return " ".join(holecards)


class Pot:
    totalpot: Decimal
    totalcollected: Decimal | None
    rake: Decimal

    def __init__(self) -> None:
        self.contenders: set[str] = set()
        self.committed: dict[str, Decimal] = {}
        self.streettotals: dict[str, Decimal | int] = {}
        self.common: dict[str, Decimal] = {}
        self.antes: dict[str, Decimal] = {}
        self.total: Decimal | None = None
        self.returned: dict[str, Decimal] = {}
        self.sym = "$"  # this is the default currency symbol
        self.pots: list[tuple[Decimal, set[str]]] = []
        self.handid = 0
        self.stp: Decimal | int = 0

    def setSym(self, sym) -> None:
        self.sym = sym

    def addPlayer(self, player) -> None:
        self.committed[player] = Decimal(0)
        self.common[player] = Decimal(0)
        self.antes[player] = Decimal(0)

    def removePlayer(self, player) -> None:
        del self.committed[player]
        del self.common[player]
        del self.antes[player]

    def addFold(self, player) -> None:
        # addFold must be called when a player folds
        self.contenders.discard(player)

    def addCommonMoney(self, player, amount) -> None:
        self.common[player] += amount

    def addAntes(self, player, amount) -> None:
        self.antes[player] += amount

    def addMoney(self, player, amount) -> None:
        # addMoney must be called for any actions that put money in the pot, in the order they occur
        self.contenders.add(player)
        self.committed[player] += amount

    def removeMoney(self, player, amount) -> None:
        self.committed[player] -= amount
        self.returned[player] = amount

    def setSTP(self, amount) -> None:
        self.stp = amount

    def markTotal(self, street) -> None:
        self.streettotals[street] = sum(self.committed.values()) + sum(self.common.values()) + self.stp

    def getTotalAtStreet(self, street):
        if street in self.streettotals:
            return self.streettotals[street]
        return 0

    def end(self, totalcollected) -> None:
        """Finalizes the state of the hand after totalPot has been calculated.
        Does not redo pot calculations but uses the already determined results.
        Can be used to validate final totals and potentially use pot.collected
        information to calculate net profits per player.
        """
        log.debug("Finalizing hand end state...")

        # Verify that totalcollected matches self.totalcollected if defined
        if self.totalcollected is None:
            self.totalcollected = totalcollected
        elif self.totalcollected != totalcollected:
            log.error(
                f"Mismatch: totalcollected passed to end({totalcollected}) does not match "
                f"self.totalcollected ({self.totalcollected})",
            )
            msg = "Mismatch in collected amounts at hand end"
            raise FpdbParseError(msg)

        # At this point, everything has already been calculated by totalPot().
        # Optionally, net gains can be calculated.
        # net_collected = collected + returned - committed
        # This calculation will be done where necessary, for example in DerivedStats or during final display.
        # Here, we simply finalize without recalculating the pot.

        # For example, to validate that the rake is consistent:
        if self.rake > self.totalpot * Decimal("0.25"):
            log.error(
                f"Suspicious rake: {self.rake:.2f} exceeds 25% of total pot {self.totalpot:.2f}",
            )
            msg = "Rake exceeds allowed percentage"
            raise FpdbParseError(msg)

        log.debug(
            f"Hand end finalization complete. totalpot={self.totalpot}, rake={self.rake}",
        )

        # No recalculations are done here. We rely on the already prepared data.

    def calculate_rake(self) -> None:
        """Calculates and distributes the rake for the total pot."""
        log.debug("Starting rake calculation...")

        rake_percentage = Decimal("0.05")  # Example: 5% rake
        max_rake = Decimal("3.00")  # Maximum rake
        minimum_pot_for_rake = Decimal(
            "1.00",
        )  # No rake applied if the total pot is below this value

        if self.total is None:
            self.total = (
                sum(self.committed.values(), Decimal(0)) + sum(self.common.values(), Decimal(0)) + Decimal(self.stp)
            )
        total = self.total

        # Calculate the rake on the main pot
        if total < minimum_pot_for_rake:
            self.rake = Decimal("0.00")
            log.debug(
                "Total pot below the minimum threshold for rake. No rake applied.",
            )
        else:
            self.rake = min(total * rake_percentage, max_rake)
            log.debug(f"Rake calculated: {self.rake:.2f}")

        # Apply the rake to the main pot only
        if self.pots:
            main_pot, participants = self.pots[0]
            if len(participants) > 1:  # Apply rake only if the pot is contested
                log.debug(f"Main pot before rake deduction: {main_pot:.2f}")
                self.pots[0] = (main_pot - self.rake, participants)
                self.total = total - self.rake
                log.debug(f"Main pot after rake deduction: {self.pots[0][0]:.2f}")
            else:
                log.debug("Main pot is uncontested. No rake applied.")

        log.debug(
            f"Rake calculation complete. Rake: {self.rake:.2f}, Total pot: {self.total:.2f}",
        )

    def __str__(self) -> str:
        if self.sym is None:
            self.sym = "C"
        if self.total is None:
            # NB: Original comment suggested calling end() here if idempotent,
            # but end() requires totalcollected parameter and may modify state.
            # Instead, calculate total for display without modifying self.total
            log.debug("Total pot not calculated, computing from committed amounts for display")
            calculated_total = sum(self.committed.values()) + sum(self.common.values()) + self.stp
            if calculated_total == 0:
                return f"Total pot {self.sym}0.00"
            # Use calculated_total for display instead of self.total
            ret = f"Total pot {self.sym}{calculated_total:.2f}"
            if len(self.pots) < 2:
                return ret
            if self.pots and len(self.pots) > 0:
                ret += f" Main pot {self.sym}{self.pots[0][0]:.2f}"
                if len(self.pots) > 1:
                    ret += "".join([f" Side pot {self.sym}{self.pots[x][0]:.2f}." for x in range(1, len(self.pots))])
            return ret

        ret = f"Total pot {self.sym}{self.total:.2f}"
        if len(self.pots) < 2:
            return ret
        ret += f" Main pot {self.sym}{self.pots[0][0]:.2f}"
        return ret + "".join(
            [(f" Side pot {self.sym}{self.pots[x][0]:.2f}.") for x in range(1, len(self.pots))],
        )


def hand_factory(hand_id, config, db_connection):
    # a factory function to discover the base type of the hand
    # and to return a populated class instance of the correct hand

    log.debug(f"get info from db for hand {hand_id}")
    gameinfo = db_connection.get_gameinfo_from_hid(hand_id)

    if gameinfo is None:
        log.error(f"No game info found for hand ID {hand_id}")
        return None  # Return None or handle the error appropriately

    log.debug(f"gameinfo {gameinfo} for hand {hand_id}")

    hand_instance: Hand
    if gameinfo["base"] == "hold":
        hand_instance = HoldemOmahaHand(
            config=config,
            hhc=None,
            sitename=gameinfo["sitename"],
            gametype=gameinfo,
            handText=None,
            builtFrom="DB",
            handid=hand_id,
        )
    elif gameinfo["base"] == "stud":
        hand_instance = StudHand(
            config=config,
            hhc=None,
            sitename=gameinfo["sitename"],
            gametype=gameinfo,
            handText=None,
            builtFrom="DB",
            handid=hand_id,
        )
    elif gameinfo["base"] == "draw":
        hand_instance = DrawHand(
            config=config,
            hhc=None,
            sitename=gameinfo["sitename"],
            gametype=gameinfo,
            handText=None,
            builtFrom="DB",
            handid=hand_id,
        )
    else:
        log.error(f"Unknown game base type: {gameinfo['base']} for hand {hand_id}")
        return None  # Handle unexpected game types

    log.debug(f"selecting info from db for hand {hand_id}")
    hand_instance.select(db_connection, hand_id)
    hand_instance.handid_selected = hand_id  # hand_instance does not supply this, create it here
    log.debug(f"exiting hand_factory for hand {hand_id}")

    return hand_instance
