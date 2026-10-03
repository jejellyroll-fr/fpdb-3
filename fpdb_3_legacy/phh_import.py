"""Import Poker Hand History (PHH) files as an external hand-history format (#381).

PHH (https://phh.readthedocs.io) is a TOML interchange format for poker hands, the one
public datasets and PokerKit use. Here it is an *input* format: a PHH hand is turned into
fpdb's own model -- ``HoldemOmahaHand``, ``StudHand`` or ``DrawHand`` -- by the same
``Hand.add*`` calls a room parser makes, then stored by the pipeline every other hand goes
through. PHH does not replace that model and no room parser is involved.

What this module will not do is guess. A variant with no lossless fpdb counterpart, an
action that breaks the betting order, a showdown that names no winner: each is refused with
a :class:`PHHImportError` naming the file, the hand and the reason, and the hand is counted
rather than stored with invented values.

Hands are stored under a ``PHH`` data-source site: the database needs a site for every hand
and player, and a dataset is not a poker room, so it gets none of a room's configuration --
no hand-history parser, no ``supported_sites`` entry, no HUD.

The PHH <-> fpdb matrix and the conventions are documented in ``docs/phh-import.md``.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import time
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

#: The extensions of one hand (``.phh``) and of several (``.phhs``, numbered TOML tables).
PHH_EXTENSIONS: Final = (".phh", ".phhs")
#: The data-source site PHH hands are stored under.
PHH_SITE_NAME: Final = "PHH"
PHH_SITE_CODE: Final = "PH"
PHH_SITE_ID: Final = 150


@dataclass(frozen=True)
class PHHGameMapping:
    """One PHH variant and the fpdb game it is stored as."""

    variant: str
    name: str
    base: str
    category: str
    limit_type: str
    lossless: bool


#: Every PHH variant, mapped explicitly. All eleven have an fpdb game that holds them
#: without loss; anything else is refused by :func:`mapping_for`.
GAMES: Final = {
    "FT": PHHGameMapping("FT", "Fixed-limit Texas hold 'em", "hold", "holdem", "fl", True),
    "NT": PHHGameMapping("NT", "No-limit Texas hold 'em", "hold", "holdem", "nl", True),
    "NS": PHHGameMapping("NS", "No-limit short-deck hold 'em", "hold", "6_holdem", "nl", True),
    "PO": PHHGameMapping("PO", "Pot-limit Omaha hold 'em", "hold", "omahahi", "pl", True),
    "FO/8": PHHGameMapping("FO/8", "Fixed-limit Omaha hold 'em hi/lo", "hold", "omahahilo", "fl", True),
    "F7S": PHHGameMapping("F7S", "Fixed-limit seven card stud", "stud", "studhi", "fl", True),
    "F7S/8": PHHGameMapping("F7S/8", "Fixed-limit seven card stud hi/lo", "stud", "studhilo", "fl", True),
    "FR": PHHGameMapping("FR", "Fixed-limit razz", "stud", "razz", "fl", True),
    "N2L1D": PHHGameMapping("N2L1D", "No-limit 2-7 lowball single draw", "draw", "27_1draw", "nl", True),
    "F2L3D": PHHGameMapping("F2L3D", "Fixed-limit 2-7 lowball triple draw", "draw", "27_3draw", "fl", True),
    "FB": PHHGameMapping("FB", "Fixed-limit badugi", "draw", "badugi", "fl", True),
}

#: The fields every PHH hand needs, per family (PHH's required-field table).
_REQUIRED: Final = {
    "hold": ("antes", "blinds_or_straddles", "starting_stacks", "actions"),
    "draw": ("antes", "blinds_or_straddles", "starting_stacks", "actions"),
    "stud": ("antes", "bring_in", "small_bet", "big_bet", "starting_stacks", "actions"),
}

_STREETS: Final = {
    "hold": ("PREFLOP", "FLOP", "TURN", "RIVER"),
    "stud": ("THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"),
}
_DRAW_STREETS: Final = {
    "27_1draw": ("DEAL", "DRAWONE"),
    "27_3draw": ("DEAL", "DRAWONE", "DRAWTWO", "DRAWTHREE"),
    "badugi": ("DEAL", "DRAWONE", "DRAWTWO", "DRAWTHREE"),
}
#: How many board cards each hold'em street deals.
_BOARD_SIZES: Final = {"FLOP": 3, "TURN": 1, "RIVER": 1}

_CARD_RE: Final = re.compile(r"[2-9TJQKA?][cdhs?]")
_ACTION_RE: Final = re.compile(
    r"^(?:(?P<dealer>d)\s+(?P<deal>dh|db)(?:\s+(?P<target>p\d+))?\s+(?P<cards>\S+)|"
    r"(?P<player>p\d+)\s+(?P<move>pb|cbr|cc|f|sd|sm)(?:\s+(?P<arg>\S+))?)$"
)
_TABLE_HEADER_RE: Final = re.compile(r"^\[\s*([^\[\].]+?)\s*\]\s*(?:#.*)?$")


# -- errors and results -----------------------------------------------------------------


class PHHImportError(ValueError):
    """A PHH hand that cannot be imported reliably.

    ``kind`` is ``"unsupported"`` for a variant or structure fpdb cannot hold without loss,
    ``"malformed"`` for a hand that breaks the format or the betting rules.
    """

    def __init__(self, kind: str, message: str, *, source: str = "", hand: str = "") -> None:
        where = ", ".join(part for part in (source, f"hand {hand}" if hand else "") if part)
        super().__init__(f"{where}: {message}" if where else message)
        self.kind = kind
        self.reason = message
        self.source = source
        self.hand = hand


UNSUPPORTED: Final = "unsupported"
MALFORMED: Final = "malformed"


@dataclass
class PHHImportResult:
    """What an import found and did."""

    discovered: int = 0
    imported: int = 0
    duplicates: int = 0
    unsupported: int = 0
    malformed: int = 0
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def add_failure(self, error: PHHImportError) -> None:
        if error.kind == UNSUPPORTED:
            self.unsupported += 1
        else:
            self.malformed += 1
        self.errors.append(str(error))

    def summary(self) -> str:
        return (
            f"PHH: {self.discovered} hands found, {self.imported} imported, {self.duplicates} duplicates, "
            f"{self.unsupported} unsupported, {self.malformed} malformed, in {self.seconds:.1f}s"
        )


def is_phh_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in PHH_EXTENSIONS


def mapping_for(variant: Any, *, source: str = "", hand: str = "") -> PHHGameMapping:
    """The fpdb game of a PHH variant; anything not in :data:`GAMES` is refused."""
    mapping = GAMES.get(str(variant))
    if mapping is None:
        known = ", ".join(GAMES)
        msg = f"variant {variant!r} has no fpdb mapping (supported: {known})"
        raise PHHImportError(UNSUPPORTED, msg, source=source, hand=hand)
    if not mapping.lossless:  # pragma: no cover - every mapped variant is lossless today
        raise PHHImportError(UNSUPPORTED, f"variant {variant!r} would be stored with loss", source=source, hand=hand)
    return mapping


# -- reading ----------------------------------------------------------------------------


@dataclass(frozen=True)
class PHHDocument:
    """One hand as read from a file, before it is interpreted."""

    source: str
    label: str  # the table name in a .phhs, the file name for a .phh
    line: int
    data: Mapping[str, Any]

    @property
    def where(self) -> str:
        return f"{self.source}:{self.line}"


def _parse_toml(text: str, source: str, line: int, label: str) -> dict[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise PHHImportError(MALFORMED, f"not valid TOML ({error})", source=f"{source}:{line}", hand=label) from None


def iter_documents(path: str | Path) -> Iterator[PHHDocument | PHHImportError]:
    """Every hand of a PHH file, one at a time.

    A ``.phhs`` file is read line by line and cut at its top-level ``[name]`` tables, so a
    large dataset is never held in memory whole. A hand whose TOML does not parse is yielded
    as the :class:`PHHImportError` it raised, in its place, so the hands after it still come.
    """
    path = Path(path)
    if path.suffix.lower() == ".phhs":
        yield from _iter_tables(path)
        return
    source = str(path)
    try:
        yield PHHDocument(source, path.name, 1, _parse_toml(path.read_text(encoding="utf-8"), source, 1, path.name))
    except PHHImportError as error:
        yield error


def _document(source: str, label: str, start: int, lines: list[str]) -> PHHDocument | PHHImportError:
    try:
        return PHHDocument(source, label, start, _parse_toml("".join(lines), source, start, label))
    except PHHImportError as error:
        return error


def _iter_tables(path: Path) -> Iterator[PHHDocument | PHHImportError]:
    """The hands of a ``.phhs`` file: one top-level TOML table each, read as they come."""
    source = str(path)
    label: str | None = None
    start = 1
    lines: list[str] = []
    preamble_reported = False
    with path.open(encoding="utf-8") as handle:
        for number, raw in enumerate(handle, start=1):
            header = _TABLE_HEADER_RE.match(raw.strip()) if raw[:1] == "[" else None
            if header is not None:
                if label is not None:
                    yield _document(source, label, start, lines)
                label, start, lines = header.group(1).strip("\"' "), number, []
            elif label is not None:
                lines.append(raw)
            elif raw.strip() and not raw.lstrip().startswith("#") and not preamble_reported:
                # A .phhs holds hands only in [name] tables; what comes before belongs to none.
                preamble_reported = True
                yield PHHImportError(MALFORMED, "content before the first [hand] table", source=f"{source}:{number}")
    if label is not None:
        yield _document(source, label, start, lines)


# -- interpreting -----------------------------------------------------------------------


def _amount(value: Any, what: str, fail: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise fail(f"{what} is not a number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise fail(f"{what} is not a number: {value!r}") from None
    if not amount.is_finite() or amount < 0:
        raise fail(f"{what} must be a finite non-negative number, not {value!r}")
    return amount


def _cards(text: str, fail: Any) -> list[str]:
    """``AsKh??`` -> ``['As', 'Kh', '0x']``; ``-`` (unknown, at showdown) -> ``[]``."""
    if text == "-":
        return []
    cards = [text[i : i + 2] for i in range(0, len(text), 2)]
    if len(text) % 2 or any(_CARD_RE.fullmatch(card) is None for card in cards):
        raise fail(f"{text!r} is not a list of cards")
    return ["0x" if "?" in card else card for card in cards]


def _known(cards: Sequence[str]) -> bool:
    return bool(cards) and all(card != "0x" for card in cards)


def hand_number(data: Mapping[str, Any]) -> int:
    """A stable number for a hand: a hash of its content, so the same hand is a duplicate.

    The hand's own ``hand`` field is not used alone: two datasets that both number their
    hands from 1 would otherwise be taken for each other's duplicates.
    """
    canonical = json.dumps(data, sort_keys=True, default=str, ensure_ascii=False)
    digest = hashlib.blake2b(canonical.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") >> 2  # 62 bits: positive in every BIGINT


def _start_time(data: Mapping[str, Any]) -> datetime.datetime:
    """The hand's start in UTC (naive, as fpdb stores it); the epoch when PHH gives no date."""
    year, month, day = data.get("year"), data.get("month"), data.get("day")
    moment = data.get("time")
    if isinstance(moment, datetime.datetime):
        local = moment
    elif isinstance(year, int) and isinstance(month, int) and isinstance(day, int):
        clock = moment if isinstance(moment, datetime.time) else datetime.time(0, 0)
        try:
            local = datetime.datetime.combine(datetime.date(year, month, day), clock.replace(tzinfo=None))
        except ValueError:
            return datetime.datetime(1970, 1, 1)
    else:
        return datetime.datetime(1970, 1, 1)
    if local.tzinfo is None and isinstance(data.get("time_zone"), str):
        try:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: PLC0415 - only for dated hands

            local = local.replace(tzinfo=ZoneInfo(data["time_zone"]))
        except (ZoneInfoNotFoundError, ValueError):
            pass
    if local.tzinfo is not None:
        local = local.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return local


@dataclass
class _Seat:
    name: str
    seat: int
    stack: Decimal
    behind: Decimal
    contributed: Decimal = Decimal(0)
    folded: bool = False


class _Builder:
    """Plays one PHH hand onto an fpdb Hand, keeping the betting state to translate it."""

    def __init__(self, document: PHHDocument, mapping: PHHGameMapping, config: Any) -> None:
        self.document = document
        self.data = document.data
        self.mapping = mapping
        self.config = config
        self.base = mapping.base

    def fail(self, message: str, kind: str = MALFORMED) -> PHHImportError:
        return PHHImportError(kind, message, source=self.document.where, hand=self.document.label)

    # -- the table ------------------------------------------------------------------
    def _seats(self) -> list[_Seat]:
        stacks = self.data["starting_stacks"]
        if not isinstance(stacks, list) or len(stacks) < 2:
            raise self.fail("starting_stacks must list at least two players")
        if any(stack is None for stack in stacks):
            raise self.fail("a starting stack is unknown (null): the hand cannot be accounted for", UNSUPPORTED)
        count = len(stacks)
        names = self.data.get("players") or [f"p{index}" for index in range(1, count + 1)]
        seats = self.data.get("seats") or list(range(1, count + 1))
        if len(names) != count or len(seats) != count:
            raise self.fail("players, seats and starting_stacks do not have the same length")
        if len({str(name) for name in names}) != count or len(set(seats)) != count:
            raise self.fail("two players share a name or a seat")
        result = []
        for index, (name, seat, stack) in enumerate(zip(names, seats, stacks, strict=True), start=1):
            if not isinstance(seat, int) or seat < 1:
                raise self.fail(f"seat {seat!r} is not a seat number")
            amount = _amount(stack, f"starting stack of p{index}", self.fail)
            result.append(_Seat(str(name), seat, amount, amount))
        return result

    def _per_player(self, key: str, count: int) -> list[Decimal]:
        values = self.data.get(key)
        if values is None:
            return [Decimal(0)] * count
        if not isinstance(values, list) or len(values) != count:
            raise self.fail(f"{key} must have one value per player")
        return [_amount(value, f"{key}[{index}]", self.fail) for index, value in enumerate(values)]

    def _gametype(self, blinds: list[Decimal]) -> dict[str, Any]:
        currency = str(self.data.get("currency") or "play")
        if self.base == "stud":
            small = _amount(self.data["small_bet"], "small_bet", self.fail)
            sb = bb = small
        else:
            posted = sorted(blind for blind in blinds if blind > 0)
            if not posted:
                raise self.fail("no blind is posted", UNSUPPORTED)
            sb, bb = (posted[0], posted[1]) if len(posted) > 1 else (posted[0] / 2, posted[0])
        return {
            "type": "ring",
            "base": self.base,
            "category": self.mapping.category,
            "limitType": self.mapping.limit_type,
            "sb": sb,
            "bb": bb,
            "currency": currency,
            "mix": "none",
            "maxSeats": None,
            "ante": Decimal(0),
        }

    # -- building -------------------------------------------------------------------
    def build(self) -> Any:
        from fpdb_3_legacy.Hand import DrawHand, HoldemOmahaHand, StudHand  # noqa: PLC0415 - Qt-free, but heavy

        for key in _REQUIRED[self.base]:
            if key not in self.data:
                raise self.fail(f"missing required field {key!r}")
        seats = self._seats()
        count = len(seats)
        antes = self._per_player("antes", count)
        blinds = self._per_player("blinds_or_straddles", count) if self.base != "stud" else [Decimal(0)] * count
        gametype = self._gametype(blinds)
        hand_class = {"hold": HoldemOmahaHand, "stud": StudHand, "draw": DrawHand}[self.base]
        number = hand_number(self.data)
        # The concrete class (stud, draw) is chosen here; typed Any for the methods only it has.
        hand: Any = hand_class(self.config, _PHHSource(self.document.source), PHH_SITE_NAME, gametype, "", "PHH", number)
        hand.handid = number
        hand.tablename = str(self.data.get("table") or self.data.get("event") or Path(self.document.source).stem)
        hand.maxseats = int(self.data.get("seat_count") or max(seat.seat for seat in seats))
        hand.startTime = _start_time(self.data)
        hero = self.data.get("_hero")
        hand.hero = str(hero) if hero in {seat.name for seat in seats} else ""
        # Button games: the last player has the button (the PHH convention). Stud has none.
        hand.buttonpos = seats[-1].seat if self.base != "stud" else 0
        for seat in seats:
            hand.addPlayer(seat.seat, seat.name, str(seat.stack))

        self.hand = hand
        self.seats = seats
        self.by_ref = {f"p{index}": seat for index, seat in enumerate(seats, start=1)}
        self.streets = _STREETS.get(self.base) or _DRAW_STREETS[self.mapping.category]
        self.street_index = 0
        self.street_bets = {seat.name: Decimal(0) for seat in seats}
        self.level = Decimal(0)
        self.dealt_this_street: set[str] = set()
        self.acted_this_street = False
        self.boards = 0
        self.cards: dict[str, list[str]] = {seat.name: [] for seat in seats}

        self._post(antes, blinds)
        actions = self.data["actions"]
        if not isinstance(actions, list) or not all(isinstance(action, str) for action in actions):
            raise self.fail("actions must be a list of strings")
        for index, raw in enumerate(actions, start=1):
            text = raw.split("#", 1)[0].strip()
            if text:
                try:
                    self._act(text)
                except PHHImportError as error:
                    raise self.fail(f"action {index} {raw.strip()!r}: {error.reason}", error.kind) from None
        self._collect()
        return hand

    @property
    def street(self) -> str:
        return self.streets[self.street_index]

    def _next_street(self) -> None:
        if self.street_index + 1 >= len(self.streets):
            raise self.fail(f"more streets than {self.mapping.variant} has")
        self.street_index += 1
        self.street_bets = dict.fromkeys(self.street_bets, Decimal(0))
        self.level = Decimal(0)
        self.dealt_this_street = set()
        self.acted_this_street = False

    def _post(self, antes: list[Decimal], blinds: list[Decimal]) -> None:
        for seat, ante in zip(self.seats, antes, strict=True):
            if ante > 0:
                ante = min(ante, seat.behind)
                self.hand.addAnte(seat.name, str(ante))
                seat.behind -= ante
                seat.contributed += ante
        if self.base == "stud":
            return
        count = len(self.seats)
        posts = list(blinds)
        if count == 2:
            # Heads-up the big blind is posted by p1 and the small blind by p2, who has the
            # button (PokerKit, which defines PHH, reverses the first two entries).
            posts[0], posts[1] = posts[1], posts[0]
        button_blind = count > 2 and posts[0] == 0 and posts[1] == 0 and posts[-1] > 0
        for index, (seat, amount) in enumerate(zip(self.seats, posts, strict=True)):
            if amount <= 0:
                continue
            if button_blind and index == count - 1:
                kind = "button blind"
            elif count == 2:
                kind = "big blind" if index == 0 else "small blind"
            else:
                kind = {0: "small blind", 1: "big blind"}.get(index, "straddle")
            amount = min(amount, seat.behind)
            self.hand.addBlind(seat.name, kind, str(amount))
            seat.behind -= amount
            seat.contributed += amount
            self.street_bets[seat.name] += amount
            self.level = max(self.level, self.street_bets[seat.name])

    def _seat(self, ref: str) -> _Seat:
        seat = self.by_ref.get(ref)
        if seat is None:
            raise self.fail(f"{ref} is not one of the {len(self.seats)} players")
        return seat

    def _act(self, text: str) -> None:
        match = _ACTION_RE.match(text)
        if match is None:
            raise self.fail("not a PHH action")
        if match.group("dealer"):
            self._deal(match.group("deal"), match.group("target"), match.group("cards"))
            return
        seat = self._seat(match.group("player"))
        move, arg = match.group("move"), match.group("arg")
        if move == "sm":
            self._show(seat, arg)
            return
        if seat.folded:
            raise self.fail(f"{seat.name} acts after folding")
        if move == "sd":
            self._draw(seat, arg)
            return
        if arg is not None and move != "cbr":
            raise self.fail(f"'{move}' takes no amount")
        if seat.behind <= 0 and move in ("cbr", "cc", "pb"):
            raise self.fail(f"{seat.name} is all in and cannot act")
        self.acted_this_street = True
        if move == "f":
            seat.folded = True
            self.hand.addFold(self.street, seat.name)
        else:
            {"cc": self._check_or_call, "pb": self._bring_in}.get(move, lambda s: self._bet(s, arg))(seat)

    def _check_or_call(self, seat: _Seat) -> None:
        to_call = min(self.level - self.street_bets[seat.name], seat.behind)
        if to_call <= 0:
            self.hand.addCheck(self.street, seat.name)
            return
        self.hand.addCall(self.street, seat.name, str(to_call))
        self._put_in(seat, to_call)

    def _bring_in(self, seat: _Seat) -> None:
        if self.base != "stud" or self.street_index:
            raise self.fail("a bring-in is only posted on third street in stud")
        amount = min(_amount(self.data["bring_in"], "bring_in", self.fail), seat.behind)
        self.hand.addBringIn(seat.name, str(amount))
        self._put_in(seat, amount)

    def _bet(self, seat: _Seat, arg: str | None) -> None:
        """``cbr``: complete, bet or raise *to* the amount (the street's total, PHH's meaning)."""
        if arg is None:
            raise self.fail("'cbr' needs the amount bet or raised to")
        total = _amount(arg, "the bet", self.fail)
        added = total - self.street_bets[seat.name]
        if total <= self.level or added <= 0:
            raise self.fail(f"a bet or raise to {total} does not exceed the current bet of {self.level}")
        if added > seat.behind:
            raise self.fail(f"{seat.name} bets {added} with {seat.behind} behind")
        if self.level == 0:
            self.hand.addBet(self.street, seat.name, str(added))
        else:
            self.hand.addRaiseTo(self.street, seat.name, str(total))
        self._put_in(seat, added)

    def _put_in(self, seat: _Seat, amount: Decimal) -> None:
        seat.behind -= amount
        seat.contributed += amount
        self.street_bets[seat.name] += amount
        self.level = max(self.level, self.street_bets[seat.name])

    def _deal(self, kind: str, target: str | None, text: str) -> None:
        cards = _cards(text, self.fail)
        if kind == "db":
            if self.base != "hold" or target is not None:
                raise self.fail("only hold'em games deal a board")
            self.boards += 1
            if self.boards > len(_BOARD_SIZES):
                raise self.fail("more than three board deals: run-it-twice boards are not supported", UNSUPPORTED)
            self._next_street()
            if len(cards) != _BOARD_SIZES[self.street]:
                raise self.fail(f"the {self.street.lower()} deals {_BOARD_SIZES[self.street]} cards, not {len(cards)}")
            self.hand.setCommunityCards(self.street, cards)
            return
        if target is None:
            raise self.fail("'d dh' needs the player dealt to")
        seat = self._seat(target)
        if self.base == "hold":
            if self.street_index or self.acted_this_street:
                raise self.fail("hole cards are dealt before any action")
            self._hole(seat, "PREFLOP", closed=cards)
        elif self.base == "stud":
            self._stud_deal(seat, cards)
        else:
            self._draw_deal(seat, cards)

    def _hole(self, seat: _Seat, street: str, *, open: list[str] | None = None, closed: list[str]) -> None:
        self.cards[seat.name] = [*self.cards[seat.name], *(open or []), *closed]
        if _known([*(open or []), *closed]) or open:
            self.hand.addHoleCards(street, seat.name, open=open or [], closed=closed, dealt=seat.name == self.hand.hero)

    def _stud_deal(self, seat: _Seat, cards: list[str]) -> None:
        if seat.name in self.dealt_this_street:
            # Dealt again: the previous street is over.
            self._next_street()
        if seat.name in self.dealt_this_street:
            raise self.fail(f"{seat.name} is dealt twice on one street")
        self.dealt_this_street.add(seat.name)
        street = self.street
        expected = 3 if street == "THIRD" else 1
        if len(cards) != expected:
            raise self.fail(f"{street.lower()} street deals {expected} cards, not {len(cards)}")
        previous = list(self.cards[seat.name])
        self.cards[seat.name] = [*previous, *cards]
        if street == "THIRD":
            self.hand.addPlayerCards(seat.name, street, open=[cards[2]], closed=cards[:2])
        elif street == "SEVENTH":
            self.hand.addPlayerCards(seat.name, street, open=[], closed=cards)
        else:
            self.hand.addPlayerCards(seat.name, street, open=cards, closed=previous)

    def _draw_deal(self, seat: _Seat, cards: list[str]) -> None:
        if self.street_index == 0:
            if self.acted_this_street or seat.name in self.dealt_this_street:
                raise self.fail("the hands are dealt once, before any action")
            self.dealt_this_street.add(seat.name)
            self._hole(seat, "DEAL", closed=cards)
            return
        # Cards drawn after this street's discards: kept cards stay closed, new ones open.
        if seat.name in self.dealt_this_street:
            raise self.fail(f"{seat.name} draws twice on one street")
        self.dealt_this_street.add(seat.name)
        kept = self.cards[seat.name]
        self.cards[seat.name] = [*kept, *cards]
        if _known([*kept, *cards]):
            self.hand.addHoleCards(self.street, seat.name, open=cards, closed=kept, dealt=seat.name == self.hand.hero)

    def _draw(self, seat: _Seat, text: str | None) -> None:
        if self.base != "draw":
            raise self.fail("only draw games stand pat or discard")
        if self.street_index == 0 or self.acted_this_street:
            self._next_street()
        discarded = _cards(text, self.fail) if text else []
        if not discarded:
            self.hand.addStandsPat(self.street, seat.name)
            return
        held = self.cards[seat.name]
        if _known(discarded):
            missing = [card for card in discarded if card not in held]
            if _known(held) and missing:
                raise self.fail(f"{seat.name} discards {' '.join(missing)}, which they do not hold")
            self.cards[seat.name] = [card for card in held if card not in discarded]
            self.hand.addDiscard(self.street, seat.name, len(discarded), " ".join(discarded))
        else:
            self.cards[seat.name] = held[: max(0, len(held) - len(discarded))]
            self.hand.addDiscard(self.street, seat.name, len(discarded))

    def _show(self, seat: _Seat, text: str | None) -> None:
        cards = _cards(text, self.fail) if text else []
        if not cards:
            # "sm" alone, or "sm -": the cards go back unseen.
            self.hand.mucked.add(seat.name)
            return
        if _known(cards):
            self.hand.addShownCards(cards, seat.name, shown=True)
        # A partly shown hand ("??Kd") names no complete holding to store.

    # -- results --------------------------------------------------------------------
    def _returned(self) -> dict[str, Decimal]:
        """The uncalled bet: what the deepest contributor put in above anyone else."""
        ordered = sorted(self.seats, key=lambda seat: seat.contributed, reverse=True)
        top, second = ordered[0], ordered[1]
        surplus = top.contributed - second.contributed
        return {top.name: surplus} if surplus > 0 else {}

    def _collect(self) -> None:
        winnings = self.data.get("winnings")
        finishing = self.data.get("finishing_stacks")
        count = len(self.seats)
        if winnings is not None:
            collected = self._per_player("winnings", count)
        elif finishing is not None:
            returned = self._returned()
            finals = self._per_player("finishing_stacks", count)
            collected = [
                final - (seat.stack - seat.contributed + returned.get(seat.name, Decimal(0)))
                for seat, final in zip(self.seats, finals, strict=True)
            ]
            if any(amount < 0 for amount in collected):
                raise self.fail("finishing_stacks are lower than the betting allows")
        else:
            live = [seat for seat in self.seats if not seat.folded]
            if len(live) != 1:
                raise self.fail(
                    "the hand reaches a showdown but gives no winnings or finishing_stacks: "
                    "its winners cannot be stated without guessing",
                    UNSUPPORTED,
                )
            pot = sum((seat.contributed for seat in self.seats), Decimal(0))
            pot -= sum(self._returned().values(), Decimal(0))
            collected = [pot if seat is live[0] else Decimal(0) for seat in self.seats]
        for seat, amount in zip(self.seats, collected, strict=True):
            if amount > 0:
                self.hand.addCollectPot(seat.name, str(amount))


class _PHHSource:
    """The ``hhc`` a Hand is built with: only its source path is read."""

    def __init__(self, in_path: str) -> None:
        self.in_path = in_path


class _PHHConfig:
    """Enough configuration to build a Hand outside the importer, when none is given."""

    def __init__(self, site_id: int = PHH_SITE_ID) -> None:
        self.site_id = site_id

    def get_site_id(self, sitename: str) -> int:
        return self.site_id

    def get_import_parameters(self) -> dict[str, Any]:
        return {"saveActions": True, "callFpdbHud": False, "cacheSessions": False, "publicDB": False}


def build_hand(document: PHHDocument, config: Any = None) -> Any:
    """The fpdb Hand a PHH hand describes, or :class:`PHHImportError`."""
    data = document.data
    if "variant" not in data:
        raise PHHImportError(MALFORMED, "missing required field 'variant'", source=document.where, hand=document.label)
    mapping = mapping_for(data["variant"], source=document.where, hand=document.label)
    try:
        return _Builder(document, mapping, config or _PHHConfig()).build()
    except PHHImportError:
        raise
    except Exception as error:  # noqa: BLE001 - Hand.py's own refusal of a hand that does not add up.
        raise PHHImportError(
            MALFORMED, f"{type(error).__name__}: {error}", source=document.where, hand=document.label
        ) from error


# -- storing ----------------------------------------------------------------------------

_SITE_LOOKUP_SQL: Final = "SELECT id FROM Sites WHERE id = %s"
_SITE_INSERT_SQL: Final = "INSERT INTO Sites (id, name, code) VALUES (%s, %s, %s)"


def ensure_phh_site(db: Any) -> int:
    """The PHH data-source row of the Sites table, created when a database has none yet."""
    placeholder = db.sql.query.get("placeholder", "%s")
    cursor = db.get_cursor()
    cursor.execute(_SITE_LOOKUP_SQL.replace("%s", placeholder), (PHH_SITE_ID,))
    if cursor.fetchone() is None:
        cursor.execute(_SITE_INSERT_SQL.replace("%s", placeholder), (PHH_SITE_ID, PHH_SITE_NAME, PHH_SITE_CODE))
        db.commit()
    return PHH_SITE_ID


class _ImportConfig(_PHHConfig):
    """The real configuration's import settings, with the PHH site id."""

    def __init__(self, config: Any) -> None:
        super().__init__()
        self.config = config

    def get_import_parameters(self) -> dict[str, Any]:
        getter = getattr(self.config, "get_import_parameters", None)
        parameters = dict(getter()) if callable(getter) else super().get_import_parameters()
        parameters["callFpdbHud"] = False
        return parameters

    def __getattr__(self, name: str) -> Any:
        return getattr(self.config, name)


def import_file(db: Any, config: Any, path: str | Path, *, file_id: int = 0) -> PHHImportResult:
    """Import every hand of one PHH file into *db*; what was found and done."""
    from fpdb_3_legacy.Exceptions import FpdbHandDuplicate  # noqa: PLC0415
    from fpdb_3_legacy.http_capture_hand_builder import import_fpdb_hand  # noqa: PLC0415

    started = time.monotonic()
    result = PHHImportResult()
    ensure_phh_site(db)
    build_config = _ImportConfig(config)
    for item in iter_documents(path):
        result.discovered += 1
        if isinstance(item, PHHImportError):
            result.add_failure(item)
            continue
        try:
            hand = build_hand(item, build_config)
        except PHHImportError as error:
            result.add_failure(error)
            continue
        # Each hand is stored and committed on its own: empty the shared bulk buffers first,
        # or the previous hand's rows would be inserted again (as the CoinPoker feed does).
        db.resetBulkCache()
        try:
            import_fpdb_hand(hand, db, file_id=file_id)
        except FpdbHandDuplicate:
            result.duplicates += 1
            continue
        except Exception as error:  # noqa: BLE001 - one hand the database refuses must not stop the file.
            db.rollback()
            db.resetBulkCache()
            result.add_failure(PHHImportError(MALFORMED, f"not stored: {error}", source=item.where, hand=item.label))
            continue
        result.imported += 1
    result.seconds = time.monotonic() - started
    return result
