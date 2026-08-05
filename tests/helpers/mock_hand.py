"""Shared MockHand for parser-style unit tests.

Legacy parser tests (`test/test_*ToFpdb.py`) write into a hand object via
a fixed set of `add*` / `set*` methods inherited from
`fpdb_3_legacy.Hand.Hand`. Each test file used to redefine its own
MockHand with subtly different field layouts, accumulating maintenance
debt as the parser surface grew. This helper consolidates the parser
write-side mock into a single class.

Two convenience constructors:

    ParserMockHand(hand_text, gametype, in_path="")
        Bovada-style: full attribute set with structured `antes`,
        `bringIn`, `blinds`, `pot_winners` containers and dict-form
        players. Use for tests that introspect those structures.

    ParserMockHand.minimal(gametype=None)
        Bare attribute set with no hand_text and empty everything.
        Use for tests that only care about the `add*` call log.

Method coverage: addPlayer, addAnte, addBringIn, addBlind, addFold,
addCheck, addCall, addBet, addRaise, addRaiseTo, addAllIn,
addComplete, addHoleCards, addCards, addShownCards, addCollectPot,
setCommunityCards, setUncalledBets.

Each action is appended to `self.actions` as a tuple
`(street, player, action_type, amount_or_None)` so callers can assert
on call order without depending on the internal storage choices of
any particular subclass.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

_STREETS_HOLDEM = ["PREFLOP", "FLOP", "TURN", "RIVER"]
_STREETS_ALL = [
    "PREFLOP",
    "FLOP",
    "TURN",
    "RIVER",
    "SHOWDOWN",
    "DEAL",
    "THIRD",
    "FOURTH",
    "FIFTH",
    "SIXTH",
    "SEVENTH",
]


class ParserMockHand:
    """Capture-only fake of fpdb_3_legacy.Hand.Hand for parser tests."""

    def __init__(self, hand_text: str = "", gametype: dict[str, Any] | None = None, in_path: str = "") -> None:
        self.handText = hand_text
        self.handtext = hand_text  # some parsers read the lowercase form
        self.gametype: dict[str, Any] = dict(gametype) if gametype else {}
        self.in_path = in_path

        # Identity
        self.handid: str | None = None
        self.startTime = None
        self.tablename: str | None = None
        self.sitename: str | None = None
        self.hero: str = ""
        self.dbid_hands: int = 1
        self.playerIds: dict[str, int] = {}
        self.version: str | None = None
        self.speed: str | None = None

        # Seats / players (dict form: {"seat": int, "name": str, "stack": Decimal})
        self.players: list[dict[str, Any]] = []
        self.stacks: dict[str, Decimal] = {}
        self.buttonpos: int | None = None
        self.maxseats: int = 0
        self.counted_seats: int = 0

        # Tournament metadata
        self.tourNo: str | None = None
        self.tourneyId: int | None = None
        self.tourneyName: str | None = None
        self.tourneyTypeId: int | None = None
        self.buyin: Decimal | None = None
        self.fee: Decimal | None = None
        self.buyinCurrency: str | None = None
        self.level: int | None = None
        self.mixed: str | None = None
        self.isSng: bool = False
        self.isRebuy: bool = False
        self.isAddOn: bool = False
        self.isKO: bool = False
        self.koBounty: Decimal | None = None
        self.koCounts: dict[str, int] = {}
        self.isProgressive: bool = False
        self.isMatrix: bool = False
        self.isShootout: bool = False

        # Streets
        self.streets: dict[str, str] = {s: "" for s in _STREETS_ALL}
        self.actionStreets: list[str] = _STREETS_HOLDEM.copy()
        self.communityStreets: list[str] = ["FLOP", "TURN", "RIVER"]
        self.holeStreets: list[str] = ["PREFLOP"]
        self.allStreets: list[str] = _STREETS_HOLDEM.copy()

        # Blinds / antes / bring-in
        self.sb: Decimal | None = None
        self.bb: Decimal | None = None
        self.antes: dict[str, Decimal] = {}
        self.bringIn: dict[str, Any] = {}
        self.blinds: list[dict[str, Any]] = []
        self.allInBlind: bool = False
        self.uncalledBets: bool = True

        # Cards
        self.community_cards: dict[str, list[str]] = {s: [] for s in self.communityStreets}
        self.board: dict[str, list[str]] = {}
        self.hole_cards: dict[str, dict[str, Any]] = {}
        self.holecards: dict[str, Any] = {}
        self.shown_cards: dict[str, list[str]] = {}
        self.shown: dict[str, Any] = {}
        self.mucked: dict[str, Any] = {}
        self.dealt: set = set()

        # Action log
        self.actions: list[tuple[str, str, str, Decimal | None]] = []

        # Pot / rake
        self.pot_winners: list[dict[str, Any]] = []
        self.collected: list[Any] = []
        self.totalcollected: Decimal = Decimal(0)
        self.totalpot: Decimal | None = None
        self.rake: Decimal | None = None

        # Misc parser-set flags
        self.isZonePoker: bool = False
        self.cancelled: bool = False
        self.runItTimes: int = 0
        self.lastBet: dict[str, Decimal] = {s: Decimal(0) for s in self.allStreets}

    # --- Class helpers -------------------------------------------------

    @classmethod
    def minimal(cls, gametype: dict[str, Any] | None = None) -> ParserMockHand:
        return cls(hand_text="", gametype=gametype or {})

    # --- Parser write surface -----------------------------------------

    def _dec(self, amount: Any) -> Decimal:
        if isinstance(amount, Decimal):
            return amount
        if amount is None:
            return Decimal(0)
        return Decimal(str(amount))

    def addPlayer(self, seat_no: int, name: str, stack: str) -> None:
        amount = self._dec(stack)
        self.players.append({"seat": seat_no, "name": name, "stack": amount})
        self.stacks[name] = amount

    def addAnte(self, player: str, amount: str) -> None:
        self.antes[player] = self._dec(amount)

    def addBringIn(self, *args: Any) -> None:
        # Both signatures observed in legacy parsers:
        #   addBringIn(player, amount)
        #   addBringIn(street, player, amount)
        if len(args) == 2:
            player, amount = args
        elif len(args) == 3:
            _, player, amount = args
        else:
            return
        self.bringIn = {"player": player, "amount": self._dec(amount)}

    def addBlind(self, player: str, blind_type: str, amount: str) -> None:
        self.blinds.append({"player": player, "type": blind_type, "amount": self._dec(amount)})

    def setUncalledBets(self, value: bool) -> None:
        self.uncalledBets = bool(value)

    def setCommunityCards(self, street: str, cards: list[str]) -> None:
        self.community_cards[street] = list(cards)

    def addHoleCards(self, street: str, player: str, **kwargs: Any) -> None:
        self.hole_cards.setdefault(player, {})[street] = kwargs

    def addCards(self, street: str, player: str, cards: list[str]) -> None:
        self.hole_cards.setdefault(player, {})[street] = {"cards": list(cards)}

    def addFold(self, street: str, player: str) -> None:
        self.actions.append((street, player, "fold", None))

    def addCheck(self, street: str, player: str) -> None:
        self.actions.append((street, player, "check", None))

    def addCall(self, street: str, player: str, amount: str) -> None:
        self.actions.append((street, player, "call", self._dec(amount)))

    def addBet(self, street: str, player: str, amount: str) -> None:
        self.actions.append((street, player, "bet", self._dec(amount)))

    def addRaise(self, street: str, player: str, amount: str) -> None:
        self.actions.append((street, player, "raise", self._dec(amount)))

    def addRaiseTo(self, street: str, player: str, amount: str) -> None:
        self.actions.append((street, player, "raise", self._dec(amount)))

    def addAllIn(self, street: str, player: str, amount: str) -> None:
        self.actions.append((street, player, "allin", self._dec(amount)))

    def addComplete(self, street: str, player: str, amount: str) -> None:
        self.actions.append((street, player, "complete", self._dec(amount)))

    def addShownCards(self, cards: list[str], player: str, *_a: Any, **_kw: Any) -> None:
        self.shown_cards[player] = list(cards)

    def addCollectPot(self, player: str, pot: str) -> None:
        amount = self._dec(pot)
        self.pot_winners.append({"player": player, "amount": amount})
        self.totalcollected += amount


# Backward-compatible alias for files that just imported "MockHand".
MockHand = ParserMockHand
