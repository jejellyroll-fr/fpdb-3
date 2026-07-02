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
from typing import Any, Dict, List, Optional, Tuple


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

    def __init__(self, hand_text: str = "", gametype: Optional[Dict[str, Any]] = None, in_path: str = "") -> None:
        self.handText = hand_text
        self.handtext = hand_text  # some parsers read the lowercase form
        self.gametype: Dict[str, Any] = dict(gametype) if gametype else {}
        self.in_path = in_path

        # Identity
        self.handid: Optional[str] = None
        self.startTime = None
        self.tablename: Optional[str] = None
        self.sitename: Optional[str] = None
        self.hero: str = ""
        self.dbid_hands: int = 1
        self.playerIds: Dict[str, int] = {}
        self.version: Optional[str] = None
        self.speed: Optional[str] = None

        # Seats / players (dict form: {"seat": int, "name": str, "stack": Decimal})
        self.players: List[Dict[str, Any]] = []
        self.stacks: Dict[str, Decimal] = {}
        self.buttonpos: Optional[int] = None
        self.maxseats: int = 0
        self.counted_seats: int = 0

        # Tournament metadata
        self.tourNo: Optional[str] = None
        self.tourneyId: Optional[int] = None
        self.tourneyName: Optional[str] = None
        self.tourneyTypeId: Optional[int] = None
        self.buyin: Optional[Decimal] = None
        self.fee: Optional[Decimal] = None
        self.buyinCurrency: Optional[str] = None
        self.level: Optional[int] = None
        self.mixed: Optional[str] = None
        self.isSng: bool = False
        self.isRebuy: bool = False
        self.isAddOn: bool = False
        self.isKO: bool = False
        self.koBounty: Optional[Decimal] = None
        self.koCounts: Dict[str, int] = {}
        self.isProgressive: bool = False
        self.isMatrix: bool = False
        self.isShootout: bool = False

        # Streets
        self.streets: Dict[str, str] = {s: "" for s in _STREETS_ALL}
        self.actionStreets: List[str] = _STREETS_HOLDEM.copy()
        self.communityStreets: List[str] = ["FLOP", "TURN", "RIVER"]
        self.holeStreets: List[str] = ["PREFLOP"]
        self.allStreets: List[str] = _STREETS_HOLDEM.copy()

        # Blinds / antes / bring-in
        self.sb: Optional[Decimal] = None
        self.bb: Optional[Decimal] = None
        self.antes: Dict[str, Decimal] = {}
        self.bringIn: Dict[str, Any] = {}
        self.blinds: List[Dict[str, Any]] = []
        self.allInBlind: bool = False
        self.uncalledBets: bool = True

        # Cards
        self.community_cards: Dict[str, List[str]] = {s: [] for s in self.communityStreets}
        self.board: Dict[str, List[str]] = {}
        self.hole_cards: Dict[str, Dict[str, Any]] = {}
        self.holecards: Dict[str, Any] = {}
        self.shown_cards: Dict[str, List[str]] = {}
        self.shown: Dict[str, Any] = {}
        self.mucked: Dict[str, Any] = {}
        self.dealt: set = set()

        # Action log
        self.actions: List[Tuple[str, str, str, Optional[Decimal]]] = []

        # Pot / rake
        self.pot_winners: List[Dict[str, Any]] = []
        self.collected: List[Any] = []
        self.totalcollected: Decimal = Decimal(0)
        self.totalpot: Optional[Decimal] = None
        self.rake: Optional[Decimal] = None

        # Misc parser-set flags
        self.isZonePoker: bool = False
        self.cancelled: bool = False
        self.runItTimes: int = 0
        self.lastBet: Dict[str, Decimal] = {s: Decimal(0) for s in self.allStreets}

    # --- Class helpers -------------------------------------------------

    @classmethod
    def minimal(cls, gametype: Optional[Dict[str, Any]] = None) -> "ParserMockHand":
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

    def setCommunityCards(self, street: str, cards: List[str]) -> None:
        self.community_cards[street] = list(cards)

    def addHoleCards(self, street: str, player: str, **kwargs: Any) -> None:
        self.hole_cards.setdefault(player, {})[street] = kwargs

    def addCards(self, street: str, player: str, cards: List[str]) -> None:
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

    def addShownCards(self, cards: List[str], player: str, *_a: Any, **_kw: Any) -> None:
        self.shown_cards[player] = list(cards)

    def addCollectPot(self, player: str, pot: str) -> None:
        amount = self._dec(pot)
        self.pot_winners.append({"player": player, "amount": amount})
        self.totalcollected += amount


# Backward-compatible alias for files that just imported "MockHand".
MockHand = ParserMockHand
