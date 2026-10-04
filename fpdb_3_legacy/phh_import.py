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
import math
import re
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

from fpdb.compat import toml_module

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

#: The fields every PHH hand needs, per family, then per limit (PHH's required-field table):
#: no and pot limit size their bets from ``min_bet``, fixed limit from the two bet sizes.
_REQUIRED: Final = {
    "hold": ("antes", "blinds_or_straddles", "starting_stacks", "actions"),
    "draw": ("antes", "blinds_or_straddles", "starting_stacks", "actions"),
    "stud": ("antes", "bring_in", "starting_stacks", "actions"),
}
_REQUIRED_BY_LIMIT: Final = {"nl": ("min_bet",), "pl": ("min_bet",), "fl": ("small_bet", "big_bet")}

_STREETS: Final = {
    "hold": ("PREFLOP", "FLOP", "TURN", "RIVER"),
    "stud": ("THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"),
}
_DRAW_STREETS: Final = {
    "27_1draw": ("DEAL", "DRAWONE"),
    "27_3draw": ("DEAL", "DRAWONE", "DRAWTWO", "DRAWTHREE"),
    "badugi": ("DEAL", "DRAWONE", "DRAWTWO", "DRAWTHREE"),
}
#: How many cards a hand starts with, for the games whose hand is dealt at once.
_HAND_SIZES: Final = {
    "holdem": 2,
    "6_holdem": 2,
    "omahahi": 4,
    "omahahilo": 4,
    "27_1draw": 5,
    "27_3draw": 5,
    "badugi": 4,
}
#: How many board cards each hold'em street deals.
_BOARD_SIZES: Final = {"FLOP": 3, "TURN": 1, "RIVER": 1}

#: A known card, or ``??`` for one that is not: PHH has no half-known card ("A?", "?s").
_CARD_RE: Final = re.compile(r"[2-9TJQKA][cdhs]|\?\?")
_CENT: Final = Decimal("0.01")
_ACTION_RE: Final = re.compile(
    r"^(?:(?P<dealer>d)\s+(?P<deal>dh|db)(?:\s+(?P<target>p\d+))?\s+(?P<cards>\S+)|"
    r"(?P<player>p\d+)\s+(?P<move>pb|cbr|cc|f|sd|sm)(?:\s+(?P<arg>\S+))?)$"
)
#: A top-level table, one hand of a ``.phhs``: a quoted key (its dots are literal) or a
#: bare one. A dotted key (``[1.notes]``) is a sub-table of the hand it follows.
_TABLE_HEADER_RE: Final = re.compile(
    r"^\[\s*(?:\"(?P<basic>(?:[^\"\\]|\\.)*)\"|'(?P<literal>[^']*)'|(?P<bare>[A-Za-z0-9_-]+))\s*\]\s*(?:#.*)?$"
)


# -- errors and results -----------------------------------------------------------------


class PHHImportError(ValueError):
    """A PHH hand that cannot be imported reliably.

    ``kind`` is ``"unsupported"`` for a variant or structure fpdb cannot hold without loss,
    ``"malformed"`` for a hand that breaks the format or the betting rules, ``"partial"``
    for a history that stops before the hand is over.
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
#: A history that stops before the hand ends, as PHH allows: counted, never stored, since
#: a hand with no result would bend every statistic it reached.
PARTIAL: Final = "partial"


@dataclass
class PHHImportResult:
    """What an import found and did."""

    discovered: int = 0
    imported: int = 0
    duplicates: int = 0
    unsupported: int = 0
    malformed: int = 0
    partial: int = 0
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def add_failure(self, error: PHHImportError) -> None:
        if error.kind == UNSUPPORTED:
            self.unsupported += 1
        elif error.kind == PARTIAL:
            self.partial += 1
        else:
            self.malformed += 1
        self.errors.append(str(error))

    def summary(self) -> str:
        return (
            f"PHH: {self.discovered} hands found, {self.imported} imported, {self.duplicates} duplicates, "
            f"{self.partial} partial, {self.unsupported} unsupported, {self.malformed} malformed, "
            f"in {self.seconds:.1f}s"
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
        toml = toml_module()
    except ModuleNotFoundError:
        # Python 3.10 (the PyOxidizer builds) without the tomli backport.
        msg = "reading PHH needs tomllib (Python 3.11+) or the tomli package"
        raise PHHImportError(UNSUPPORTED, msg, source=f"{source}:{line}", hand=label) from None
    try:
        return toml.loads(text)
    except toml.TOMLDecodeError as error:
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
    """One hand of a ``.phhs``: its table, parsed with its header so its sub-tables stay in it."""
    try:
        parsed = _parse_toml("".join(lines), source, start, label)
    except PHHImportError as error:
        return error
    if len(parsed) != 1:
        # A table that belongs to none of the hands, such as ``[2.notes]`` under ``[1]``.
        others = ", ".join(repr(key) for key in list(parsed)[1:])
        return PHHImportError(MALFORMED, f"tables of another hand: {others}", source=f"{source}:{start}", hand=label)
    ((key, data),) = parsed.items()
    return PHHDocument(source, key, start, data)


def _toml_state(line: str, open_string: str | None, depth: int) -> tuple[str | None, int]:
    """What is still open at the end of *line*: a multiline string (``\"\"\"`` or ``'''``),
    and how many arrays and inline tables.

    Single-line strings and comments are skipped so that their quotes and brackets open
    nothing; a table header opens and closes its brackets on its own line.
    """
    index = 0
    while index < len(line):
        if open_string is not None:
            index, open_string = _multiline_end(line, index, open_string)
            continue
        char = line[index]
        if char == "#":
            break
        if line.startswith(('"""', "'''"), index):
            open_string = line[index : index + 3]
            index += 3
            continue
        if char in "\"'":
            index += 1
            while index < len(line) and line[index] != char:
                index += 2 if char == '"' and line[index] == "\\" else 1
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth = max(depth - 1, 0)
        index += 1
    return open_string, depth


def _multiline_end(line: str, index: int, open_string: str) -> tuple[int, str | None]:
    """Where the multiline string open at *index* ends on *line* -- or the line's end."""
    while index < len(line):
        if open_string == '"""' and line[index] == "\\":
            index += 2  # an escaped character, a quote included
        elif line.startswith(open_string, index):
            index += 3
            # Up to two quotes more belong to the string: '""""' ends it with one quote.
            while index < len(line) and line[index] == open_string[0]:
                index += 1
            return index, None
        else:
            index += 1
    return index, open_string


def _iter_tables(path: Path) -> Iterator[PHHDocument | PHHImportError]:
    """The hands of a ``.phhs`` file: one top-level TOML table each, read as they come."""
    with path.open(encoding="utf-8") as handle:
        yield from _split_tables(str(path), enumerate(handle, start=1))


def _split_tables(source: str, numbered: Iterable[tuple[int, str]]) -> Iterator[PHHDocument | PHHImportError]:
    """Cut numbered lines at their top-level ``[name]`` headers: one hand each."""
    label: str | None = None
    start = 1
    lines: list[str] = []
    suspects: list[int] = []
    preamble_reported = False
    open_string: str | None = None
    depth = 0
    for number, raw in numbered:
        stripped = raw.strip()
        # A line of a multiline string ("[second]" in a note) or of an array ("_x = [" then
        # "[1]") is a value, never a header: only the document's top level has headers.
        inside = open_string is not None or depth > 0
        open_string, depth = _toml_state(raw, open_string, depth)
        header = _TABLE_HEADER_RE.match(stripped) if stripped[:1] == "[" else None
        if header is not None and not inside:
            if label is not None:
                yield from _documents(source, label, start, lines, suspects)
            label = next(key for key in header.group("basic", "literal", "bare") if key is not None)
            start, lines, suspects = number, [raw], []
        elif label is not None:
            if header is not None:
                suspects.append(len(lines))  # a hand of its own if the value around it never closes
            lines.append(raw)
        elif stripped and not stripped.startswith("#") and not preamble_reported:
            # A .phhs holds hands only in [name] tables; what comes before belongs to none.
            preamble_reported = True
            yield PHHImportError(MALFORMED, "content before the first [hand] table", source=f"{source}:{number}")
    if label is not None:
        yield from _documents(source, label, start, lines, suspects)


def _documents(
    source: str, label: str, start: int, lines: list[str], suspects: list[int]
) -> Iterator[PHHDocument | PHHImportError]:
    """One hand's table -- or, when a value it leaves open swallowed the hands after it, the
    malformed hand and then those hands, cut again from the first header inside that value."""
    document = _document(source, label, start, lines)
    if not isinstance(document, PHHImportError) or document.kind != MALFORMED or not suspects:
        yield document
        return
    cut = suspects[0]
    yield _document(source, label, start, lines[:cut])
    yield from _split_tables(source, enumerate(lines[cut:], start=start + cut))


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
    if amount != amount.quantize(_CENT, rounding=ROUND_DOWN):
        # fpdb stores every amount in hundredths: a finer one would be truncated silently.
        raise fail(f"{what} is {value!r}: fpdb stores amounts to two decimal places", UNSUPPORTED)
    return amount


def _cards(text: str, fail: Any) -> list[str]:
    """``AsKh??`` -> ``['As', 'Kh', '0x']``; ``-`` (unknown, at showdown) -> ``[]``."""
    if text == "-":
        return []
    cards = [text[i : i + 2] for i in range(0, len(text), 2)]
    if len(text) % 2 or any(_CARD_RE.fullmatch(card) is None for card in cards):
        raise fail(f"{text!r} is not a list of cards")
    return ["0x" if "?" in card else card for card in cards]


def _any_known(cards: Sequence[str]) -> bool:
    return any(card != "0x" for card in cards)


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


def _start_time(data: Mapping[str, Any], fail: Any) -> datetime.datetime:
    """The hand's start in UTC (naive, as fpdb stores it); the epoch when PHH gives no year."""
    _check_time_fields(data, fail)
    year, month, day = data.get("year"), data.get("month"), data.get("day")
    moment = data.get("time")
    if isinstance(moment, datetime.datetime):
        local = moment
    elif any(part is not None for part in (year, month, day, moment)):
        # PHH's fields are optional one by one (its own example gives only the year): each
        # one given is kept, each one missing is the epoch's (1970, January, the 1st, 00:00).
        year, month, day = (
            part if part is not None else default for part, default in ((year, 1970), (month, 1), (day, 1))
        )
        clock = moment if isinstance(moment, datetime.time) else datetime.time(0, 0)
        try:
            local = datetime.datetime.combine(datetime.date(year, month, day), clock.replace(tzinfo=None))
        except ValueError:
            raise fail(f"{year}-{month}-{day} is not a date") from None
    else:
        if data.get("time_zone") is not None:
            _zone(data["time_zone"], fail)  # a zone that does not exist is malformed, dated or not
        return datetime.datetime(1970, 1, 1)
    return _in_utc(local, data, fail)


def _check_time_fields(data: Mapping[str, Any], fail: Any) -> None:
    """The date and time fields, when given, are of their PHH type."""
    year, month, day = data.get("year"), data.get("month"), data.get("day")
    moment = data.get("time")
    if moment is not None and not isinstance(moment, (datetime.datetime, datetime.time)):
        raise fail(f"time {moment!r} is not a time")
    # The epoch stands for a hand PHH gives no date; a date given wrong is not that.
    if any(part is not None and (not isinstance(part, int) or isinstance(part, bool)) for part in (year, month, day)):
        raise fail(f"year, month and day {year!r}, {month!r}, {day!r} are not a date")
    for key in ("time_zone", "time_zone_abbreviation"):
        if data.get(key) is not None and not isinstance(data[key], str):
            raise fail(f"{key} {data[key]!r} is not a string")


def _in_utc(local: datetime.datetime, data: Mapping[str, Any], fail: Any) -> datetime.datetime:
    """*local* in UTC (naive), by its own offset or the hand's ``time_zone``."""
    abbreviation = data.get("time_zone_abbreviation")
    if local.tzinfo is None and data.get("time_zone") is not None:
        wall = local
        local = local.replace(tzinfo=_zone(data["time_zone"], fail))
        # A wall time skipped when summer time begins never happened: it round-trips to
        # another one, whichever fold.
        folds = [fold for fold in (0, 1) if _round_trip(local.replace(fold=fold)) == wall]
        if not folds:
            raise fail(f"{wall:%Y-%m-%d %H:%M} does not exist in {data['time_zone']} (the clocks skip it)")
        if abbreviation is not None:
            # The abbreviation says which of a repeated hour (the end of summer time) it is.
            folds = [fold for fold in folds if local.replace(fold=fold).tzname() == abbreviation]
            if not folds:
                raise fail(f"{abbreviation!r} is not {data['time_zone']}'s abbreviation at {wall:%Y-%m-%d %H:%M}")
        local = local.replace(fold=folds[0])
    location = [str(data[key]) for key in ("city", "region", "country") if data.get(key)]
    if local.tzinfo is None and abbreviation is None and location and data.get("time") is not None:
        # PHH reads a time with no zone as local to the hand's location, which fpdb does not
        # resolve to a zone: stored as UTC, it would be off by hours.
        raise fail(f"the time is local to {', '.join(location)}, with no time_zone to convert it", UNSUPPORTED)
    if local.tzinfo is None and abbreviation is not None and abbreviation.upper() not in ("UTC", "GMT", "Z"):
        # An abbreviation alone is ambiguous (CST is America's or China's): the hand's time
        # cannot be put in UTC, and stored as UTC it would be off by hours.
        raise fail(f"time_zone_abbreviation {abbreviation!r} without a time_zone cannot be converted", UNSUPPORTED)
    if local.tzinfo is not None:
        local = local.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return local


def _round_trip(aware: datetime.datetime) -> datetime.datetime:
    """The wall time *aware* reads after a trip through UTC (naive)."""
    return aware.astimezone(datetime.timezone.utc).astimezone(aware.tzinfo).replace(tzinfo=None)


def _zone(name: str, fail: Any) -> datetime.tzinfo:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones  # noqa: PLC0415 - dated hands only

    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        if not available_timezones():
            # No time-zone database here (a build without tzdata): the zone may be valid.
            raise fail(f"no time-zone database to convert {name!r}", UNSUPPORTED) from None
        raise fail(f"{name!r} is not a time zone") from None


def _player_names(given: Sequence[Any]) -> list[str]:
    """The players' names; an unnamed one is pN, or pN#2... when the file already uses that."""
    supplied = {str(name) for name in given if name not in (None, "")}
    names: list[str] = []
    for index, name in enumerate(given, start=1):
        if name not in (None, ""):
            names.append(str(name))
            continue
        fallback, suffix = f"p{index}", 1
        while fallback in supplied or fallback in names:
            suffix += 1
            fallback = f"p{index}#{suffix}"
        names.append(fallback)
    return names


@dataclass
class _Seat:
    name: str
    seat: int
    stack: Decimal
    behind: Decimal
    contributed: Decimal = Decimal(0)
    antes: Decimal = Decimal(0)
    folded: bool = False
    #: Mucked at showdown ("sm" alone): out of every pot, as a fold would be.
    mucked: bool = False


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

    def _cards(self, text: str) -> list[str]:
        """Cards, refused when the variant's deck has no such card (short deck: no 2 to 5)."""
        cards = _cards(text, self.fail)
        if self.mapping.category == "6_holdem":
            missing = [card for card in cards if card[0] in "2345"]
            if missing:
                raise self.fail(f"{' '.join(missing)} is not in a short deck")
        return cards

    # -- the table ------------------------------------------------------------------
    def _seats(self) -> list[_Seat]:
        stacks = self.data["starting_stacks"]
        if not isinstance(stacks, list) or len(stacks) < 2:
            raise self.fail("starting_stacks must list at least two players")
        if any(stack is None or (isinstance(stack, float) and math.isinf(stack)) for stack in stacks):
            # PHH writes an unknown starting stack as null or inf.
            raise self.fail("a starting stack is unknown: the hand cannot be accounted for", UNSUPPORTED)
        count = len(stacks)
        # PHH allows an empty name for a player it does not know: that one is called pN.
        names = _player_names(self.data.get("players") or [""] * count)
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
            if amount <= 0:
                raise self.fail(f"the starting stack of p{index} must be positive")
            result.append(_Seat(str(name), seat, amount, amount))
        return result

    def _seat_count(self, seats: Sequence[_Seat]) -> int:
        """The table size: ``seat_count``, which must hold every seat, or else the highest seat."""
        highest = max(seat.seat for seat in seats)
        given = self.data.get("seat_count")
        if given is None:
            return highest
        if not isinstance(given, int) or isinstance(given, bool) or given < highest:
            raise self.fail(f"seat_count {given!r} does not hold seat {highest}")
        return given

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

        for key in (*_REQUIRED[self.base], *_REQUIRED_BY_LIMIT[self.mapping.limit_type]):
            if key not in self.data:
                raise self.fail(f"missing required field {key!r}")
            # The sizes a game is built from are positive; zero would let any amount through.
            if key in ("min_bet", "small_bet", "big_bet", "bring_in") and _amount(self.data[key], key, self.fail) <= 0:
                raise self.fail(f"{key} must be positive")
        seats = self._seats()
        count = len(seats)
        antes = self._per_player("antes", count)
        blinds = self._per_player("blinds_or_straddles", count) if self.base != "stud" else [Decimal(0)] * count
        gametype = self._gametype(blinds)
        hand_class = {"hold": HoldemOmahaHand, "stud": StudHand, "draw": DrawHand}[self.base]
        number = hand_number(self.data)
        # The concrete class (stud, draw) is chosen here; typed Any for the methods only it has.
        hand: Any = hand_class(
            self.config, _PHHSource(self.document.source), PHH_SITE_NAME, gametype, "", "PHH", number
        )
        hand.handid = number
        hand.tablename = str(self.data.get("table") or self.data.get("event") or Path(self.document.source).stem)
        hand.maxseats = self._seat_count(seats)
        hand.startTime = _start_time(self.data, self.fail)
        hero = self.data.get("_hero")
        hand.hero = str(hero) if hero in {seat.name for seat in seats} else ""
        # Button games: the last player has the button (the PHH convention). Stud has none.
        hand.buttonpos = seats[-1].seat if self.base != "stud" else 0
        for seat in seats:
            hand.addPlayer(seat.seat, seat.name, str(seat.stack))

        self.hand = hand
        self._start_state(seats)

        self._post(antes, blinds)
        if self.base != "stud":
            # The largest live blind or straddle is the first raise to beat preflop.
            self.raise_size = self.level
            posted = [index for index, blind in enumerate(blinds) if blind > 0]
            self.last_actor = 0 if len(seats) == 2 else (posted[-1] if posted else len(seats) - 1)
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

    def _start_state(self, seats: list[_Seat]) -> None:
        """The betting state a hand is played on, before the forced bets."""
        self.seats = seats
        self.by_ref = {f"p{index}": seat for index, seat in enumerate(seats, start=1)}
        self.streets = _STREETS.get(self.base) or _DRAW_STREETS[self.mapping.category]
        self.street_index = 0
        self.street_bets = {seat.name: Decimal(0) for seat in seats}
        self.level = Decimal(0)
        self.dealt_this_street: set[str] = set()
        self.drew_this_street: set[str] = set()
        self.acted_this_street = False
        self.acted_players: set[str] = set()
        # The bet each player left the street at when they last acted. A player may raise again
        # only once it has risen by a full raise since -- one all-in for less does not reopen
        # the betting, several in a row may (no and pot limit, as PokerKit plays it).
        self.acted_at: dict[str, Decimal] = {}
        self.completed = False
        # Fourth street in stud high: once a bet or raise is the big bet, every one after is.
        self.big_bet_made = False
        # The smallest a raise may add on this street (no-limit, pot-limit), and the bets a
        # street ended with that nobody matched, kept when the street is left behind.
        self.raise_size = self.level
        self.uncalled = {seat.name: Decimal(0) for seat in seats}
        self.boards = 0
        self.cards: dict[str, list[str]] = {seat.name: [] for seat in seats}
        # Known cards in play, so one card cannot be dealt twice; discards leave it, since a
        # draw game reshuffles them when the stub runs out.
        self.seen: set[str] = set()
        # Draw games: cards discarded and not yet replaced, per player.
        self.awaiting: dict[str, int] = {seat.name: 0 for seat in seats}
        # Whose turn it is, in button games: the index of the last player to act. Preflop,
        # play starts after the last blind posted (heads-up, after the big blind, p1).
        self.last_actor = len(seats) - 1
        self.last_drawer = len(seats) - 1

    @property
    def street(self) -> str:
        return self.streets[self.street_index]

    def _next_street(self) -> None:
        live = [seat.name for seat in self.seats if not seat.folded]
        if len(live) < 2:
            raise self.fail(f"the hand is over: everyone but {live[0]} folded")
        if self.street_index + 1 >= len(self.streets):
            raise self.fail(f"more streets than {self.mapping.variant} has")
        if not self._street_closed():
            raise self.fail(f"{self.street.lower()} begins its next street before its betting is over")
        if any(self.awaiting.values()):
            raise self.fail("a discard is not replaced before the next street")
        if self.base == "draw" and self.street_index and (undrawn := self._undrawn()):
            raise self.fail(f"the next draw comes before {', '.join(undrawn)} has drawn on this one")
        if self.street_index == 0 and (undealt := self._undealt()):
            # Even an all-in runout, where nobody bets, starts from everyone's hole cards.
            raise self.fail(f"the next street comes before {', '.join(undealt)} is dealt in")
        if self.base == "stud":
            missing = [seat.name for seat in self.seats if not seat.folded and seat.name not in self.dealt_this_street]
            if missing:
                raise self.fail(f"{', '.join(missing)} gets no card on {self.street.lower()} street")
        # A bet nobody could match (everyone else all in or folded) is returned even when the
        # board is dealt on: remembered here, before the street's bets are forgotten.
        for name, amount in self._street_surplus().items():
            self.uncalled[name] += amount
        self.street_index += 1
        self.street_bets = dict.fromkeys(self.street_bets, Decimal(0))
        self.level = Decimal(0)
        self.raise_size = Decimal(0)
        self.big_bet_made = False
        self.dealt_this_street = set()
        self.drew_this_street = set()
        self.acted_this_street = False
        self.acted_players = set()
        self.acted_at = {}
        # After the deal, the first live player after the button acts and draws first.
        self.last_actor = len(self.seats) - 1
        self.last_drawer = len(self.seats) - 1

    def _post(self, antes: list[Decimal], blinds: list[Decimal]) -> None:
        if self.base != "stud" and len(self.seats) == 2:
            # Heads-up PHH assigns the first two entries of both arrays in reverse: the big
            # blind -- and a big-blind ante -- belong to p1, the small blind to p2, who has
            # the button (PokerKit, which defines PHH, does the same).
            antes = [antes[1], antes[0]]
            blinds = [blinds[1], blinds[0]]
        trimmed = bool(self.data.get("ante_trimming_status"))
        for seat, ante in zip(self.seats, antes, strict=True):
            if ante > 0:
                if trimmed and ante > seat.behind:
                    # Trimming limits a short ante's player to what everyone matched of it (an
                    # ante side pot); fpdb pools antes as common money anyone can win. Untrimmed,
                    # the short player may win every ante (PHH, PokerKit): that fpdb can say.
                    raise self.fail(
                        f"{seat.name}'s ante is trimmed to a short stack, which fpdb cannot represent", UNSUPPORTED
                    )
                ante = min(ante, seat.behind)
                self.hand.addAnte(seat.name, str(ante))
                seat.behind -= ante
                seat.contributed += ante
                seat.antes += ante
        if self.base == "stud":
            return
        count = len(self.seats)
        posts = list(blinds)
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
        if seat.folded:
            raise self.fail(f"{seat.name} acts after folding")
        if move == "sm":
            if not self._showdown_begun():
                raise self.fail(f"{seat.name} shows or mucks before the showdown")
            self._show(seat, arg)
            return
        if move == "sd":
            self._draw(seat, arg)
            return
        self._betting_move(seat, move, arg)

    def _betting_move(self, seat: _Seat, move: str, arg: str | None) -> None:
        """A fold, check, call, bring-in, bet or raise, by a player allowed to make it now."""
        if arg is not None and move != "cbr":
            raise self.fail(f"'{move}' takes no amount")
        if seat.behind <= 0:
            # Nothing left to bet, nothing to fold either: an all-in player stays in every pot
            # they are in (stud checks no turn order, which would otherwise say so).
            raise self.fail(f"{seat.name} is all in and cannot act")
        if self._street_closed():
            raise self.fail(f"{seat.name} acts after the betting on {self.street.lower()} is over")
        if undealt := self._undealt():
            raise self.fail(f"the betting begins before {', '.join(undealt)} is dealt in")
        if self.base == "stud" and self.street_index == 0 and self.level == 0 and move not in ("pb", "cbr"):
            # Third street opens with the bring-in or a completion: its player may not check or fold.
            raise self.fail(f"{seat.name} {'folds' if move == 'f' else 'checks'} before the bring-in is posted")
        if self.base != "stud":
            # Stud's order follows the best hand showing, which takes evaluating the upcards.
            self._take_turn(seat)
        self.acted_this_street = True
        self.acted_players.add(seat.name)
        if move == "f":
            seat.folded = True
            self.hand.addFold(self.street, seat.name)
        else:
            {"cc": self._check_or_call, "pb": self._bring_in}.get(move, lambda s: self._bet(s, arg))(seat)
        # Counted once the move is made, at the bet it left the street at. The bring-in is
        # forced, like a blind: a completion over it leaves its player free to raise.
        if move != "pb":
            self.acted_at[seat.name] = self.level

    def _next_in_turn(self, start: int, eligible: Any) -> int | None:
        """The first player after index *start*, round the table, that *eligible* accepts."""
        count = len(self.seats)
        for step in range(1, count + 1):
            index = (start + step) % count
            if eligible(self.seats[index]):
                return index
        return None

    def _take_turn(self, seat: _Seat) -> None:
        """A bet, call, check or fold by the player whose turn it is, in a button game."""
        expected = self._next_in_turn(self.last_actor, lambda other: not other.folded and other.behind > 0)
        index = self.seats.index(seat)
        if expected is not None and expected != index:
            raise self.fail(f"{seat.name} acts out of turn: it is {self.seats[expected].name}'s turn")
        self.last_actor = index

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
        if self.level > 0:
            raise self.fail("the bring-in is already posted, or completed")
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
        if self.level > 0 and not any(
            other is not seat and not other.folded and other.behind > 0 for other in self.seats
        ):
            # Everyone else is all in: there is nobody left to call a raise (as PokerKit plays it).
            raise self.fail(f"{seat.name} raises with everyone else all in; only a call is possible")
        self._check_size(seat, total, added)
        if self.mapping.limit_type == "fl" and total - self.level == self._fixed_sizes()[-1]:
            self.big_bet_made = True
        if self._completes():
            # Third street, facing only the bring-in -- or in its place: completing to the small bet.
            self.hand.addComplete(self.street, seat.name, str(total))
            self.completed = True
        elif self.level == 0:
            self.hand.addBet(self.street, seat.name, str(added))
        else:
            self.hand.addRaiseTo(self.street, seat.name, str(total))
        self._put_in(seat, added)

    def _check_size(self, seat: _Seat, total: Decimal, added: Decimal) -> None:
        """The amount is one the variant allows; all in for less always is.

        Fixed limit: the street's bet size (a stud completion goes to the small bet, and
        fourth street may use the big bet). No and pot limit: at least the minimum bet, or a
        raise by at least the last raise; pot limit: at most the pot after calling.
        """
        all_in = added == seat.behind
        limit = self.mapping.limit_type
        # Every structure: a player who acted may raise again only over a full raise since.
        full = min(self._fixed_sizes()) if limit == "fl" else self.raise_size
        faced = self.acted_at.get(seat.name)
        if faced is not None and self.level - faced < full:
            raise self.fail(f"{seat.name} may only call or fold: an all-in for less did not reopen the betting")
        if limit == "fl":
            sizes = self._fixed_sizes()
            allowed = {self.level + size for size in sizes} if not self._completes() else {sizes[0]}
            if total not in allowed and not (all_in and total < max(allowed)):
                raise self.fail(
                    f"a fixed-limit bet or raise goes to {' or '.join(map(str, sorted(allowed)))}, not {total}"
                )
            return
        minimum = self.level + max(self.raise_size, _amount(self.data.get("min_bet", 0), "min_bet", self.fail))
        if total < minimum and not all_in:
            raise self.fail(f"a bet or raise to {total} is below the minimum of {minimum}")
        if limit == "pl":
            pot = sum((other.contributed for other in self.seats), Decimal(0))
            maximum = self.level + pot + (self.level - self.street_bets[seat.name])
            if total > maximum:
                raise self.fail(f"a pot-limit bet or raise goes at most to {maximum}, not {total}")
        if total - self.level >= self.raise_size:
            self.raise_size = total - self.level

    def _fixed_sizes(self) -> list[Decimal]:
        """The fixed-limit bet sizes of the current street, smallest first."""
        small = _amount(self.data.get("small_bet"), "small_bet", self.fail)
        big = _amount(self.data.get("big_bet"), "big_bet", self.fail)
        early = {"hold": ("PREFLOP", "FLOP"), "stud": ("THIRD",), "draw": ("DEAL", "DRAWONE")}[self.base]
        if self.street == "FOURTH" and self.mapping.category == "studhi" and self._open_pair():
            # An open pair on fourth street lets the big bet in (stud high only); once it is
            # made, the raises after it are big bets too.
            return [big] if self.big_bet_made else [small, big]
        if self.base == "stud" and self.street == "FOURTH":
            return [small]
        return [small] if self.street in early else [big]

    def _open_pair(self) -> bool:
        """Whether a live player shows a pair on fourth street (third and fourth upcards)."""
        for seat in self.seats:
            up = self.cards[seat.name][2:4]
            if not seat.folded and len(up) == 2 and _known(up) and up[0][0] == up[1][0]:
                return True
        return False

    def _completes(self) -> bool:
        if self.base != "stud" or self.street_index or self.completed:
            return False
        bring_in = _amount(self.data["bring_in"], "bring_in", self.fail)
        return self.level <= bring_in

    def _put_in(self, seat: _Seat, amount: Decimal) -> None:
        seat.behind -= amount
        seat.contributed += amount
        self.street_bets[seat.name] += amount
        self.level = max(self.level, self.street_bets[seat.name])

    def _deal(self, kind: str, target: str | None, text: str) -> None:
        cards = self._cards(text)
        self._note_dealt(cards)
        if kind == "db":
            if target is not None:
                raise self.fail("a board is dealt to no player")
            self._deal_board(cards)
            return
        if target is None:
            raise self.fail("'d dh' needs the player dealt to")
        seat = self._seat(target)
        size = _HAND_SIZES.get(self.mapping.category)
        if size is not None and (self.base == "hold" or self.street_index == 0) and len(cards) != size:
            raise self.fail(f"{self.mapping.name} deals {size} hole cards, not {len(cards)}")
        if self.base == "hold":
            if self.street_index or self.acted_this_street:
                raise self.fail("hole cards are dealt before any action")
            self._check_deal_order(seat)
            self.dealt_this_street.add(seat.name)
            self._hole(seat, "PREFLOP", closed=cards)
        elif self.base == "stud":
            self._stud_deal(seat, cards)
        else:
            self._draw_deal(seat, cards)

    def _note_dealt(self, cards: list[str]) -> None:
        """Refuse a known card that is already in play, then count these in."""
        known = [card for card in cards if card != "0x"]
        repeated = [card for card in known if card in self.seen]
        if repeated or len(set(known)) != len(known):
            raise self.fail(f"{' '.join(repeated) or 'a card'} is dealt twice")
        self.seen.update(known)

    def _deal_board(self, cards: list[str]) -> None:
        if self.base == "stud":
            # Seventh street dealt as one shared card, when the deck runs short (eight players):
            # fpdb's stud hand has no community card to hold it.
            raise self.fail("a shared stud card (the deck ran short) is not supported", UNSUPPORTED)
        if self.base != "hold":
            raise self.fail("only hold'em games deal a board")
        self.boards += 1
        if self.boards > len(_BOARD_SIZES):
            raise self.fail("more than three board deals: run-it-twice boards are not supported", UNSUPPORTED)
        self._next_street()
        if len(cards) != _BOARD_SIZES[self.street]:
            raise self.fail(f"the {self.street.lower()} deals {_BOARD_SIZES[self.street]} cards, not {len(cards)}")
        self.hand.setCommunityCards(self.street, cards)

    def _check_deal_order(self, seat: _Seat) -> None:
        """Hole cards go round from the first player still in to the last, once each."""
        if seat.name in self.dealt_this_street:
            raise self.fail(f"{seat.name} is dealt twice")
        expected = next(
            (other for other in self.seats if not other.folded and other.name not in self.dealt_this_street), None
        )
        if expected is not None and expected is not seat:
            raise self.fail(f"{seat.name} is dealt out of turn: {expected.name} is next")

    def _undrawn(self) -> list[str]:
        """Players still in who have not stood pat or discarded on this draw."""
        return [seat.name for seat in self.seats if not seat.folded and seat.name not in self.drew_this_street]

    def _undealt(self) -> list[str]:
        """Players still in who should have their cards before this street's betting."""
        live = [seat for seat in self.seats if not seat.folded]
        if self.base == "stud" or self.street_index == 0:
            return [seat.name for seat in live if seat.name not in self.dealt_this_street]
        if self.base == "draw":
            # A draw street bets once everyone still in has drawn (or stood pat) and been served.
            return [seat.name for seat in live if seat.name not in self.drew_this_street or self.awaiting[seat.name]]
        return []

    def _hole(self, seat: _Seat, street: str, *, open: list[str] | None = None, closed: list[str]) -> None:
        self.cards[seat.name] = [*self.cards[seat.name], *(open or []), *closed]
        # Kept as soon as one card is known: the unknown ones stay "0x", fpdb's own blank.
        if _any_known([*(open or []), *closed]):
            self.hand.addHoleCards(street, seat.name, open=open or [], closed=closed, dealt=seat.name == self.hand.hero)

    def _stud_deal(self, seat: _Seat, cards: list[str]) -> None:
        if seat.name in self.dealt_this_street:
            # Dealt again: the previous street is over.
            self._next_street()
        if seat.name in self.dealt_this_street:
            raise self.fail(f"{seat.name} is dealt twice on one street")
        self._check_deal_order(seat)
        self.dealt_this_street.add(seat.name)
        street = self.street
        expected = 3 if street == "THIRD" else 1
        if len(cards) != expected:
            raise self.fail(f"{street.lower()} street deals {expected} cards, not {len(cards)}")
        previous = list(self.cards[seat.name])
        self.cards[seat.name] = [*previous, *cards]
        self._place_stud(seat.name, street, previous, cards)

    def _place_stud(self, name: str, street: str, previous: list[str], cards: list[str]) -> None:
        """A stud street's cards where fpdb reads them (``StudHand.join_holecards``)."""
        if street == "THIRD":
            self.hand.addPlayerCards(name, street, open=[cards[2]], closed=cards[:2])
        elif street == "SEVENTH" and name != self.hand.hero:
            # Only the hero's seventh card is read from the open slot, as a room shows it.
            self.hand.addPlayerCards(name, street, open=[], closed=cards)
        else:
            self.hand.addPlayerCards(name, street, open=cards, closed=previous)

    def _draw_deal(self, seat: _Seat, cards: list[str]) -> None:
        if self.street_index == 0:
            if self.acted_this_street or seat.name in self.dealt_this_street:
                raise self.fail("the hands are dealt once, before any action")
            self._check_deal_order(seat)
            self.dealt_this_street.add(seat.name)
            self._hole(seat, "DEAL", closed=cards)
            return
        # Cards drawn after this street's discards: kept cards stay closed, new ones open.
        if seat.name in self.dealt_this_street:
            raise self.fail(f"{seat.name} draws twice on one street")
        if len(cards) != self.awaiting[seat.name]:
            raise self.fail(f"{seat.name} draws {len(cards)} cards for {self.awaiting[seat.name]} discarded")
        if undrawn := self._undrawn():
            raise self.fail(f"replacements are dealt once everyone has drawn: {', '.join(undrawn)} has not")
        # Like the deal, from the first player still in to the last (those who discarded).
        expected = next(
            (
                other
                for other in self.seats
                if not other.folded and self.awaiting[other.name] and other.name not in self.dealt_this_street
            ),
            None,
        )
        if expected is not None and expected is not seat:
            raise self.fail(f"{seat.name} is dealt out of turn: {expected.name} is next")
        self.awaiting[seat.name] = 0
        self.dealt_this_street.add(seat.name)
        kept = self.cards[seat.name]
        self.cards[seat.name] = [*kept, *cards]
        if _any_known([*kept, *cards]):
            self.hand.addHoleCards(self.street, seat.name, open=cards, closed=kept, dealt=seat.name == self.hand.hero)

    def _draw(self, seat: _Seat, text: str | None) -> None:
        if self.base != "draw":
            raise self.fail("only draw games stand pat or discard")
        # A draw opens the next street: after the deal, after this street's betting, or --
        # when everyone is all in and nobody bets -- when this player has drawn here already.
        if self.street_index == 0 or self.acted_this_street or seat.name in self.drew_this_street:
            self._next_street()
        expected = self._next_in_turn(
            self.last_drawer, lambda other: not other.folded and other.name not in self.drew_this_street
        )
        index = self.seats.index(seat)
        if expected is not None and expected != index:
            raise self.fail(f"{seat.name} draws out of turn: it is {self.seats[expected].name}'s turn")
        self.last_drawer = index
        self.drew_this_street.add(seat.name)
        discarded = self._cards(text) if text else []
        if not discarded:
            self.hand.addStandsPat(self.street, seat.name)
            return
        held = self.cards[seat.name]
        known = [card for card in discarded if card != "0x"]
        if len(set(known)) != len(known):
            raise self.fail(f"{seat.name} discards the same card twice")
        self.cards[seat.name] = self._discard(seat, held, discarded)
        # Every named card was this player's (held, or one of their unknown cards): it leaves
        # the hand, free to come back from a reshuffled stub.
        self.seen.difference_update(known)
        if known:
            self.hand.addDiscard(self.street, seat.name, len(discarded), " ".join(known))
        else:
            self.hand.addDiscard(self.street, seat.name, len(discarded))
        self.awaiting[seat.name] = len(discarded)

    def _discard(self, seat: _Seat, held: list[str], discarded: list[str]) -> list[str]:
        """What is left of *held* once *discarded* is gone.

        A named card leaves the hand itself -- or, when the deal did not say it, one of the
        hand's unknown cards; ``??`` takes one of the unknown cards.
        """
        remaining = list(held)
        for card in discarded:
            if card != "0x" and card in remaining:
                remaining.remove(card)
            elif "0x" in remaining:
                if card in self.seen:
                    raise self.fail(f"{seat.name} discards {card}, which is dealt elsewhere")
                remaining.remove("0x")
            elif card == "0x":
                raise self.fail(f"{seat.name} discards an unnamed card from a hand whose cards are all known")
            else:
                raise self.fail(f"{seat.name} discards {card}, which they do not hold")
        return remaining

    def _reconcile(self, seat: _Seat, dealt: list[str], shown: list[str]) -> list[str]:
        """The shown hand, checked against the deal: the cards it names are the dealt ones
        (in any order) or fill the deal's unknown or undealt cards, and its own unknown cards are the
        dealt ones it does not name -- a partly shown ``??Kd`` keeps a dealt ``As``.
        """
        # A replacement not dealt yet is a card of the hand too (the history stops early).
        pending = self.awaiting[seat.name]
        if dealt and len(shown) != len(dealt) + pending:
            raise self.fail(f"{seat.name} shows {len(shown)} cards for {len(dealt) + pending} dealt")
        named = [card for card in shown if card != "0x"]
        if len(set(named)) != len(named):
            raise self.fail(f"{seat.name} shows the same card twice")
        new = [card for card in named if card not in dealt]
        clash = [card for card in new if card in self.seen]
        if clash:
            raise self.fail(f"{seat.name} shows {' '.join(clash)}, which is dealt elsewhere")
        if dealt and len(new) > dealt.count("0x") + pending:
            raise self.fail(f"{seat.name} shows {' '.join(new)}, which the deal did not give them")
        self.seen.update(new)
        unnamed = iter(card for card in dealt if card not in named and card != "0x")
        return [card if card != "0x" else next(unnamed, "0x") for card in shown]

    def _show(self, seat: _Seat, text: str | None) -> None:
        if not text:
            # "sm" alone: the cards go back unseen, and the player's claim to the pot with them.
            self.hand.mucked.add(seat.name)
            seat.mucked = True
            return
        # "sm -" shows the cards the deal already named; anything else names them here.
        dealt = self.cards[seat.name]
        cards = list(dealt) if text == "-" else self._cards(text)
        merged = self._reconcile(seat, dealt, cards)
        if not _any_known(merged):
            return
        self.cards[seat.name] = merged
        if self.base == "hold" and seat.name == self.hand.hero:
            # fpdb's hold'em show only flags the hero as shown, trusting the dealt cards.
            self.hand.addHoleCards("PREFLOP", seat.name, closed=merged, shown=True, dealt=True)
            return
        if self.base == "stud" and seat.name == self.hand.hero:
            # Likewise in stud: the shown cards go back into each street the deal filled.
            self.hand.shown.add(seat.name)
            for index, street in enumerate(("THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH")):
                dealt_to = 3 + index
                if len(merged) < dealt_to:
                    break
                cards = merged[:3] if index == 0 else [merged[dealt_to - 1]]
                self._place_stud(seat.name, street, merged[: dealt_to - len(cards)], cards)
            return
        self.hand.addShownCards(merged, seat.name, shown=True)

    # -- results --------------------------------------------------------------------
    def _street_surplus(self) -> dict[str, Decimal]:
        """What the current street's top bettor put in above anyone else's bet on it.

        Bets, not whole contributions: antes are dead money nobody has to match.
        """
        ordered = sorted(self.street_bets.items(), key=lambda item: item[1], reverse=True)
        (top, top_bet), (_second, second_bet) = ordered[0], ordered[1]
        return {top: top_bet - second_bet} if top_bet > second_bet else {}

    def _returned(self) -> dict[str, Decimal]:
        """Every uncalled bet of the hand: earlier streets' and the last one's."""
        returned = {name: amount for name, amount in self.uncalled.items() if amount > 0}
        for name, amount in self._street_surplus().items():
            returned[name] = returned.get(name, Decimal(0)) + amount
        return returned

    def _finished(self) -> bool:
        """Whether the actions reach the end of the hand: the last street dealt and closed."""
        if self.street_index != len(self.streets) - 1:
            return False
        live = [seat for seat in self.seats if not seat.folded]
        if self.base == "hold" and self.boards < len(_BOARD_SIZES):
            return False
        if self.base == "stud" and not {seat.name for seat in live} <= self.dealt_this_street:
            return False
        if self.base == "draw" and not {seat.name for seat in live} <= self.drew_this_street:
            return False
        if any(self.awaiting.values()):
            return False
        return self._street_closed()

    def _showdown_begun(self) -> bool:
        """Whether cards may be shown: the hand's end, or an all-in runout (nobody left to bet)."""
        if self._finished():
            return True
        can_act = [seat for seat in self.seats if not seat.folded and seat.behind > 0]
        return len(can_act) <= 1 and self._street_closed() and not self._undealt()

    def _street_closed(self) -> bool:
        """Whether this street's betting is over: every player who can still act has had a
        turn and matched the bet -- one check on the river with the other player still to
        speak, or a flop dealt before the big blind's option, is a street left open."""
        can_act = [seat for seat in self.seats if not seat.folded and seat.behind > 0]
        matched = all(self.street_bets[seat.name] == self.level for seat in can_act)
        if len(can_act) <= 1:
            return matched
        return matched and all(seat.name in self.acted_players for seat in can_act)

    def _collect(self) -> None:
        # Whether the hand is over is decided by its actions, before any result is read:
        # PHH lets an ongoing hand carry zero winnings or its stacks so far.
        live = [seat for seat in self.seats if not seat.folded]
        if len(live) != 1 and not self._finished():
            raise self.fail("the history stops before the hand ends (a partial hand)", PARTIAL)
        collected = self._collected(live)
        available = sum((seat.contributed for seat in self.seats), Decimal(0))
        available -= sum(self._returned().values(), Decimal(0))
        if sum(collected, Decimal(0)) > available:
            # What is collected comes out of the pot (less the rake); fpdb would otherwise
            # grow the pot to match and store a win nobody paid for.
            raise self.fail(f"{sum(collected, Decimal(0))} is collected from a pot of {available}")
        eligible = self._eligible()
        for seat, amount in zip(self.seats, collected, strict=True):
            if amount > eligible[seat.name]:
                where = "a folded player" if seat.folded else "a mucked hand" if seat.mucked else "the pots they are in"
                raise self.fail(f"{seat.name} collects {amount}, more than {where} can win ({eligible[seat.name]})")
        # Together, too: the players capped at a pot can share it, not each take it whole.
        # Eligibility is nested (who put in more is in every pot of who put in less), so
        # checking each cap against all the players held to it is enough.
        for cap in sorted(set(eligible.values())):
            held = [amount for seat, amount in zip(self.seats, collected, strict=True) if eligible[seat.name] <= cap]
            if sum(held, Decimal(0)) > cap:
                raise self.fail(f"{sum(held, Decimal(0))} is collected from pots of {cap}")
        for seat, amount in zip(self.seats, collected, strict=True):
            if amount > 0:
                self.hand.addCollectPot(seat.name, str(amount))

    def _collected(self, live: list[_Seat]) -> list[Decimal]:
        """What each player collected: from winnings, from finishing stacks, or by a fold-out."""
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
            if len(live) != 1:
                raise self.fail(
                    "the hand reaches a showdown but gives no winnings or finishing_stacks: "
                    "its winners cannot be stated without guessing",
                    UNSUPPORTED,
                )
            pot = sum((seat.contributed for seat in self.seats), Decimal(0))
            pot -= sum(self._returned().values(), Decimal(0))
            collected = [pot if seat is live[0] else Decimal(0) for seat in self.seats]
        return collected

    def _eligible(self) -> dict[str, Decimal]:
        """The most each player could collect: the main and side pots they are in.

        Pots are cut at each player's net wager (antes aside, uncalled bets returned); a layer
        is won only by a player still in the hand who wagered at least that much. Antes are
        common money, as fpdb books them, which every player still in can win. A folded
        player, or one who mucked, is eligible for nothing.
        """
        returned = self._returned()
        net = {seat.name: seat.contributed - seat.antes - returned.get(seat.name, Decimal(0)) for seat in self.seats}
        antes = sum((seat.antes for seat in self.seats), Decimal(0))
        eligible = {seat.name: Decimal(0) if seat.folded or seat.mucked else antes for seat in self.seats}
        previous = Decimal(0)
        for level in sorted({amount for amount in net.values() if amount > 0}):
            layer = sum((min(amount, level) - min(amount, previous) for amount in net.values()), Decimal(0))
            for seat in self.seats:
                if not seat.folded and not seat.mucked and net[seat.name] >= level:
                    eligible[seat.name] += layer
            previous = level
        return eligible


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

_SITE_LOOKUP_SQL: Final = "SELECT name, code FROM Sites WHERE id = %s"
_SITE_INSERT_SQL: Final = "INSERT INTO Sites (id, name, code) VALUES (%s, %s, %s)"


def ensure_phh_site(db: Any) -> int:
    """The PHH data-source row of the Sites table, created when a database has none yet."""
    placeholder = db.sql.query.get("placeholder", "%s")
    cursor = db.get_cursor()
    cursor.execute(_SITE_LOOKUP_SQL.replace("%s", placeholder), (PHH_SITE_ID,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute(_SITE_INSERT_SQL.replace("%s", placeholder), (PHH_SITE_ID, PHH_SITE_NAME, PHH_SITE_CODE))
        db.commit()
    elif tuple(row) != (PHH_SITE_NAME, PHH_SITE_CODE):
        # Another source holds the id: its hands must not be mixed with PHH's.
        raise PHHImportError(
            UNSUPPORTED, f"site id {PHH_SITE_ID} is {row[0]!r} ({row[1]!r}) in this database, not the PHH data source"
        )
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
    try:
        ensure_phh_site(db)
    except PHHImportError as error:
        result.add_failure(PHHImportError(error.kind, error.reason, source=str(path)))
        result.seconds = time.monotonic() - started
        return result
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
