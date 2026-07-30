#!/usr/bin/env python3
"""Build normalized fpdb hand dicts from decoded CoinPoker game events.

Consumes the ``game.*`` event stream produced by ``coinpoker_protocol`` and
emits the normalized ``hand_data`` dicts consumed by
``http_capture_hand_builder.build_fpdb_hand`` (players / actions / community /
holecards / collections). Supports ring and tournament Hold'em/Omaha hands.
"""

from __future__ import annotations

import datetime
import re
from collections import defaultdict
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

from fpdb_3_legacy.coinpoker_protocol import iter_game_events
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("coinpoker_hand_builder")

# A poker table seats two to ten, so a field that names the table and answers
# outside that range is describing something else. Storing it breaks the import
# outright on MySQL, where Gametypes.maxSeats is a TINYINT and anything past
# 127 is refused.
MIN_TABLE_SEATS = 2
MAX_TABLE_SEATS = 10

_VALUE = {
    "TWO": "2",
    "THREE": "3",
    "FOUR": "4",
    "FIVE": "5",
    "SIX": "6",
    "SEVEN": "7",
    "EIGHT": "8",
    "NINE": "9",
    "TEN": "T",
    "JACK": "J",
    "QUEEN": "Q",
    "KING": "K",
    "ACE": "A",
}
_SUIT = {"SPADES": "s", "HEARTS": "h", "DIAMONDS": "d", "CLUBS": "c"}
_NUM_RANK = {10: "T", 11: "J", 12: "Q", 13: "K", 14: "A"}

# CoinPoker game hints (the GUI dropdown) -> (fpdb base, category). Used as a
# fallback when the variant can't be read from the hand itself. SHORTDECK == 6+
# Hold'em (fpdb category 6_holdem).
_CATEGORY = {
    "PLO4": ("hold", "omahahi"),
    "PLO5": ("hold", "5_omahahi"),
    "PLO6": ("hold", "6_omahahi"),
    "NLH": ("hold", "holdem"),
    "NLHE": ("hold", "holdem"),
    "SHORTDECK": ("hold", "6_holdem"),
}

# Hole-card count -> (fpdb base, category), for the counts that are unambiguous.
# CoinPoker's hand events carry no explicit game variant, but the number of cards
# dealt to the hero identifies the Omaha family, so it is detected per hand: a
# PLO5 hand keeps its 5th card even when the session hint says PLO4. Two-card
# games (Hold'em vs short-deck) are handled separately since the count is equal.
_HOLE_COUNT_CATEGORY = {
    4: ("hold", "omahahi"),
    5: ("hold", "5_omahahi"),
    6: ("hold", "6_omahahi"),
}


def _decimal_or_none(value: Any) -> Decimal | None:
    """Return a finite protocol money value, or None for blank/invalid fields."""
    try:
        amount = Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None
    return amount if amount.is_finite() else None


# Card ranks removed from a short deck (6+ Hold'em uses 6..A only). Seeing any of
# them proves a full 52-card deck, i.e. regular Hold'em.
_LOW_RANKS = frozenset({"TWO", "THREE", "FOUR", "FIVE"})

# Real size of each community street. Run-it-twice can stack extra cards under a
# street key; capping keeps every board at five cards (and avoids duplicate-card
# equity errors downstream).
_STREET_LEN = {"FLOP": 3, "TURN": 1, "RIVER": 1}


def _card(c: dict) -> str:
    return _VALUE[c["value"]] + _SUIT[c["suit"]]


def _cards(lst: list[dict]) -> list[str]:
    return [_card(c) for c in lst or []]


def _chat_card(tok: str) -> str:
    tok = tok.strip()
    suit = tok[-1].lower()
    num = int(tok[:-1])
    return _NUM_RANK.get(num, str(num)) + suit


def _first(evs: list[tuple], name: str) -> Any:
    return next((d for n, _h, d in evs if n == name and isinstance(d, dict)), None)


def _iter_dicts(value: Any):
    """Yield nested protocol objects without assuming one server response shape."""
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _iter_dicts(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_dicts(nested)


def _protocol_values(evs: list[tuple], *keys: str) -> Iterator[tuple[str, Any]]:
    """Every (spelling, value) found for these keys, in the order they appear."""
    wanted = {key.casefold() for key in keys}
    for _name, _hid, data in evs:
        for obj in _iter_dicts(data):
            for key, value in obj.items():
                if key.casefold() in wanted and value not in (None, ""):
                    yield key, value


def _protocol_value(evs: list[tuple], *keys: str) -> Any:
    """Return the first non-blank value for any spelling in nested event data."""
    for _key, value in _protocol_values(evs, *keys):
        return value
    return None


def _seat_count(value: Any, *, source: str) -> int | None:
    """A seat count, or None when the value cannot be one.

    A table seats a handful of people, so a number outside that range is
    describing something else -- and storing it breaks the import outright on
    MySQL, where the column is a TINYINT. Callers try the next candidate, and
    fall back to the players actually seated when none is usable.
    """
    if not str(value or "").isdigit():
        return None
    seats = int(value)
    if MIN_TABLE_SEATS <= seats <= MAX_TABLE_SEATS:
        return seats
    log.warning(
        "Ignoring implausible seat count %s from %s: a table seats %d to %d",
        seats,
        source,
        MIN_TABLE_SEATS,
        MAX_TABLE_SEATS,
    )
    return None


def _table_seat_count(evs: list[tuple]) -> int | None:
    """The first value naming this table that could be a number of chairs.

    Taking the first value found and validating it afterwards would let a
    field carrying nonsense hide a good one appearing later in the stream, so
    every candidate is offered until one is plausible.

    maxPlayers is deliberately not among the spellings: on a tournament table
    it answers with the entrants the tournament accepts, and a small one looks
    exactly like a table size -- no range check can tell it apart.
    """
    for key, value in _protocol_values(evs, "maxSeats", "tableSize"):
        seats = _seat_count(value, source=f"the {key} field")
        if seats is not None:
            return seats
    return None


# Sent whenever a table is joined, including when the player is moved, so it is
# the one place the tournament names itself in a way that survives a table
# change. roomProperties.id is that name; parentTournamentId is a level above
# and belongs to a *different* tournament -- the parent of one step is the id of
# the step below it, so reading that conflates the two.
TOURNAMENT_JOIN_EVENT = "tournamentlobby.join_table"

# Sent when a cash table is joined, naming the table and the room it belongs
# to. That room is what says the table is All-in or Fold: the hands themselves
# carry no variant, and the room name is a display string.
GAME_JOIN_EVENT = "lobby.join_game_table"

# The room ids CoinPoker gives its All-in or Fold lobby. Both are required:
# separately each is an ordinary number, together they have named nothing but
# an AOF room in the captures seen (regular cash is type 6 / lobby 1,
# tournament steps are type 8 / lobby 2).
AOF_TOURNAMENT_TYPE_ID = 14
AOF_LOBBY_ID = 12

# Which game a room deals, as the room itself reports it.
MINI_GAME_HOLDEM = 1
MINI_GAME_OMAHA = 2

# When neither a join nor the lobby catalogue is available -- a capture that
# began with the client already seated sees neither -- the deal order is the
# last thing left to go on. All-in or Fold puts the flop out before opening
# the betting; no other game does. Measured over fifteen captured tables the
# two do not overlap: All-in or Fold tables deal the flop first on about 98%
# of hands, ordinary ring tables on 0 to 11% (the stray few are hands the
# capture joined in the middle of). A table is read this way only after enough
# hands to tell the difference, and only when nothing better has spoken.
MIN_SHAPE_HANDS = 5
SHAPE_THRESHOLD = 0.8

FLOP_EVENT = "game.dealer_cards"
ACTION_EVENT = "game.user_turn"


def _flop_precedes_the_betting(evs: list[tuple]) -> bool | None:
    """True when the flop was dealt before anyone was asked to act.

    None when the hand shows neither, which says nothing either way.
    """
    names = [name for name, _hid, _data in evs]
    if FLOP_EVENT not in names or ACTION_EVENT not in names:
        return None
    return names.index(FLOP_EVENT) < names.index(ACTION_EVENT)


def note_deal_order(evs: list[tuple], table_id: str, hand_id: str, shape: dict[str, Any]) -> None:
    """Record which came first at this table, the flop or the betting.

    Each hand counts once. A hand is rebuilt on every sweep until it is
    complete, so counting per build weighted the long hands heavily enough to
    push a table below the threshold and leave it unrecognised.
    """
    first = _flop_precedes_the_betting(evs)
    if first is None:
        return
    seen = shape.setdefault(table_id, [0, 0, set()])
    if hand_id in seen[2]:
        return
    seen[2].add(hand_id)
    seen[0 if first else 1] += 1


def looks_like_all_in_or_fold(table_id: str, shape: dict[str, Any]) -> bool:
    """Whether this table's deal order says All-in or Fold, with enough hands."""
    before, after = shape.get(table_id, (0, 0, None))[:2]
    total = before + after
    if total < MIN_SHAPE_HANDS:
        return False
    return before / total >= SHAPE_THRESHOLD


# Every event that names the table it is talking about. They are what a hand
# can be told by; everything else in the stream speaks for the whole capture.
TABLE_JOIN_EVENTS = (TOURNAMENT_JOIN_EVENT, GAME_JOIN_EVENT)

# How many other tournament markers travel alongside the joins.
MAX_SESSION_CONTEXT = 100


def _joined_rooms(event: tuple) -> Iterator[tuple[str, dict]]:
    """The (table, room) pairs a join event names.

    The two joins are shaped differently -- a tournament join names one table
    at the top level, a cash join carries a list of them -- so callers ask
    here rather than reaching into either shape.
    """
    name, _hid, data = event
    if not isinstance(data, dict):
        return
    if name == TOURNAMENT_JOIN_EVENT:
        entries: list[Any] = [data]
    elif name == GAME_JOIN_EVENT:
        entries = list(data.get("tablesToJoin") or [])
    else:
        return
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        table = _table_from_title(entry.get("tableName"))
        room = entry.get("roomProperties")
        if table and isinstance(room, dict):
            yield table, room


# The lobby's own catalogue of All-in or Fold rooms, keyed by table. It is how
# a table played before -- or without -- its join being captured is still
# known: the join is sent once, the catalogue is broadcast repeatedly.
AOF_ROOM_CATALOGUE = "allinfoldRoomData"


def _catalogued_aof_rooms(event: tuple) -> Iterator[tuple[str, Any]]:
    """The (table, game) pairs the lobby's All-in or Fold catalogue lists.

    Read by its known shape rather than searched for: the catalogue carries
    hundreds of rooms and arrives hundreds of times, and walking all of it on
    every hand would cost more than every other reading of the stream put
    together.
    """
    data = event[2]
    if not isinstance(data, dict):
        return
    catalogue = data.get(AOF_ROOM_CATALOGUE)
    if not isinstance(catalogue, dict):
        return
    for menus in catalogue.values():
        for tables in (menus or {}).values() if isinstance(menus, dict) else ():
            for table, room in (tables or {}).items() if isinstance(tables, dict) else ():
                if isinstance(room, dict):
                    yield str(table), room.get("miniGameTypeId")


def aof_tables(evs: list[tuple]) -> dict[str, Any]:
    """The tables the room has said are All-in or Fold, and which game each is.

    A different game: there is no betting before the flop, which is dealt
    first, and the choice is the whole hand. Filed as ordinary Omaha its hands
    land among hands played normally, and neither set of statistics means
    anything afterwards.

    The value is the room's own ``miniGameTypeId``. The variant has to come
    from the room because the hand may not say: a hand whose hole cards were
    not captured falls back to the game the GUI is set to, and an All-in or
    Fold Hold'em table read through a PLO setting would otherwise be stored as
    All-in or Fold Omaha -- a game whose streets it does not have.
    """
    tables: dict[str, Any] = {}
    for event in evs:
        tables.update(_catalogued_aof_rooms(event))
        for table, room in _joined_rooms(event):
            if room.get("tournamentTypeId") == AOF_TOURNAMENT_TYPE_ID and room.get("lobbyId") == AOF_LOBBY_ID:
                tables[table] = room.get("miniGameTypeId")
    return tables


def joined_tournaments(evs: list[tuple]) -> dict[str, tuple[str, str | None]]:
    """Which tournament each joined table belongs to.

    Keyed by table because a capture carries every table at once: a player
    sitting at two tournaments and a ring game gets one stream, so a single
    "the tournament is X" would put ring hands in a tournament and hands of one
    tournament in another. The room names the table it is talking about, and
    the number ending that name is the table the hands carry.
    """
    joined: dict[str, tuple[str, str | None]] = {}
    for name, _hid, data in evs:
        if name != TOURNAMENT_JOIN_EVENT or not isinstance(data, dict):
            continue
        room = data.get("roomProperties")
        if not isinstance(room, dict) or room.get("id") is None:
            continue
        table = _table_from_title(data.get("tableName"))
        if table:
            joined[table] = (str(room["id"]), room.get("tournamentName") or None)
    return joined


def _joined_only_value(evs: list[tuple], *keys: str) -> Any:
    """As _protocol_value, but blind to the joins of other tables.

    A join describes one table. Letting a general search read one would answer
    with a tournament this table has never been in -- which is how a ring game
    played alongside a tournament came to be filed as one.
    """
    return _protocol_value([event for event in evs if event[0] not in TABLE_JOIN_EVENTS], *keys)


def _table_from_hand_id(hid: str) -> str:
    """The table a hand belongs to, read off its number.

    A hand id is the table followed by a five-digit counter (91426500343 ->
    914265), which is also the number the room shows in the window title.
    """
    try:
        return str(int(hid) // 100000)
    except (ValueError, TypeError):
        return str(hid)


def _joins_table(event: tuple, table: str) -> bool:
    """True when this carried event is a join naming `table`."""
    return any(joined == table for joined, _room in _joined_rooms(event))


def _table_from_title(title: Any) -> str | None:
    """The table number ending a room's table name, if it ends with one."""
    match = re.search(r"(\d+)\s*$", str(title or ""))
    return match.group(1) if match else None


def _tournament_info(evs: list[tuple], table_id: str = "", *, sole_table: bool = True) -> dict[str, Any] | None:
    """Extract stable MTT metadata from CoinPoker's tournament event variants.

    ``table_id`` decides whose tournament this is. A capture carries every
    table at once, so the join of one table says nothing about another: taking
    it as a sign would make a ring game played alongside a tournament into a
    tournament of its own.
    """
    joined_no, joined_name = joined_tournaments(evs).get(table_id, (None, None))
    # Everything below is read from this hand's own events. A carried marker
    # names no table, so it would say "tournament" about every table the
    # capture is carrying -- the transport port included, which is what a
    # capture watching a tournament and a ring game at once will always show.
    own = [event for event in evs if event[1] is not None]
    # What may speak for this table: its own hand's events, and the join that
    # names it. Nothing else -- a carried marker names no table, so it answers
    # for every table the capture is holding at once, and the lobby sends
    # thousands of them carrying the tournament it is about. Reading a number
    # off one is how a ring game played next to a tournament acquired that
    # tournament's id, and how a table of one tournament could acquire
    # another's buy-in.
    # When the capture is holding this table alone there is nothing for a
    # table-less marker to be confused with, so it may still speak: a room
    # that never sends a join would otherwise leave its one tournament table
    # looking like a ring game.
    mine = [*(event for event in evs if _joins_table(event, table_id)), *own]
    if sole_table:
        mine = [*evs]
    server_port = _protocol_value(own, "_coinpokerServerPort")
    tournament_transport = server_port in (3000, 3001, "3000", "3001")
    tour_no = joined_no or _joined_only_value(mine, "tournamentId", "tourneyId", "tournament_id", "tourney_id")
    tournament_event = any(
        "tournament" in event_name.casefold() or "tourney" in event_name.casefold() for event_name, _hid, _data in own
    )
    explicit_flag = _protocol_value(own, "isTournament", "tournamentTable")
    if (
        tour_no is None
        and not tournament_event
        and not tournament_transport
        and explicit_flag not in (True, 1, "1", "true", "True")
    ):
        return None

    name = joined_name or _joined_only_value(
        mine,
        "tournamentName",
        "tourneyName",
        "tournament_name",
        "tournamentShortName",
    )
    table_id = _protocol_value(mine, "tableId", "table_id", "gameTableId")
    max_seats = _table_seat_count(mine)
    buyin = _protocol_value(mine, "buyIn", "buyin", "buyInAmount", "entryFee")
    fee = _protocol_value(mine, "fee", "rake", "tournamentFee")
    bounty = _protocol_value(mine, "bounty", "bountyAmount", "knockoutBounty")
    level = _protocol_value(mine, "level", "blindLevel", "tournamentLevel")
    return {
        "tour_no": str(tour_no) if tour_no is not None else None,
        "name": str(name) if name is not None else None,
        "table_id": str(table_id) if table_id is not None else None,
        "max_seats": max_seats,
        "buyin": str(buyin) if buyin is not None else None,
        "fee": str(fee) if fee is not None else None,
        "bounty": str(bounty) if bounty is not None else None,
        "level": str(level) if level is not None else None,
    }


# The room announces where everyone finished once the tournament closes, in an
# event of its own that carries no hand id. It arrives after the last hand, so
# it is read on its own rather than ridden in on a hand.
TOURNAMENT_RESULT_EVENT = "tournamentlobby.tournament_winner_info"


def tournament_results(events: list[tuple]) -> list[dict[str, Any]]:
    """Where each paid player finished, and what they were paid.

    Only the place is reported. ``prize`` is a label, not an amount -- the
    captured tournaments pay "Ticket" -- and nothing yet says what a numeric
    one would be denominated in: fpdb stores winnings as an integer number of
    cents in a named currency, and the capture offers a coinTypeId whose
    meaning has not been established. A place is worth recording on its own;
    a number written in the wrong unit or currency is worse than no number,
    because it reads as a real result.
    """
    return [place for announcement in tournament_result_announcements(events) for place in announcement]


def tournament_result_announcements(events: list[tuple]) -> list[list[dict[str, Any]]]:
    """The places of each closing announcement, kept apart from one another.

    One list per announcement, because an evening holds more than one
    tournament and each closes with its own. Read together they are a single
    roll of names belonging to nobody in particular: the players no longer
    identify a tournament, and the places of the second go to the first or
    nowhere. They are told apart here, and answered for separately.
    """
    announcements: list[list[dict[str, Any]]] = []
    for name, _hid, data in events:
        if name != TOURNAMENT_RESULT_EVENT or not isinstance(data, dict):
            continue
        places: list[dict[str, Any]] = []
        for entry in data.get("winnerList") or []:
            if not isinstance(entry, dict):
                continue
            player = entry.get("name")
            rank = str(entry.get("rank") or "")
            if not player or not rank.isdigit():
                continue
            places.append({"player": str(player), "rank": int(rank), "prize": str(entry.get("prize") or "")})
        if places:
            announcements.append(places)
    return announcements


def build_hands_from_stream(s2c: bytes, table_category: str = "PLO4") -> list[dict[str, Any]]:
    return build_hands(list(iter_game_events(s2c)), table_category)


def build_hands(
    events: list[tuple[str, str | None, Any]],
    table_category: str = "PLO4",
    session_context: list[tuple] | None = None,
    session_tables: set[str] | None = None,
    session_aof: dict[str, Any] | None = None,
    session_shape: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Group decoded events by hand id and build a normalized dict per hand.

    ``session_context`` carries the tournament announcements across calls. The
    room announces the tournament once, when the table is joined, so a batch
    arriving later has nothing identifying it -- and a hand with no tournament
    number falls back to naming itself after its table, which changes the
    moment the player is moved. Two HUDs for one tournament is what that looks
    like. Pass the same list on every call to keep the announcement.

    ``session_aof`` remembers which tables are All-in or Fold. The room says
    so once, in a catalogue far too large to carry alongside the hands, so
    what it said is kept rather than the saying of it.

    ``session_tables`` remembers the tables this capture has dealt hands at.
    Whether a marker naming no table is ambiguous is a fact about the capture,
    not about the twenty events in hand: a sweep holding a single hand looks
    unambiguous however many tables are being played, and that is most sweeps.
    Pass the same set on every call.
    """
    order: list[str] = []
    groups: dict[str, list[tuple]] = defaultdict(list)
    aof = session_aof if session_aof is not None else {}
    aof.update(aof_tables(events))
    shape = session_shape if session_shape is not None else {}
    carried: list[tuple] = session_context if session_context is not None else []
    for name, hid, data in events:
        if hid is None:
            # Attached to the hand in progress so a late announcement still
            # reaches it -- unless it is another table's join, which would tell
            # that hand it belongs to a tournament it has never been in.
            if order and (
                name not in TABLE_JOIN_EVENTS or _joins_table((name, hid, data), _table_from_hand_id(order[-1]))
            ):
                groups[order[-1]].append((name, hid, data))
            if name in TABLE_JOIN_EVENTS:
                # One join of each kind is kept per table, and never evicted.
                # Keeping them all is what lets a player sit at several tables
                # at once, and keeping only the newest would strand the tables
                # joined before it; they are told apart by table, so none can
                # claim another's hands.
                joined = [table for table, _room in _joined_rooms((name, hid, data))]
                if joined:
                    carried[:] = [
                        event
                        for event in carried
                        if event[0] != name or not any(_joins_table(event, table) for table in joined)
                    ]
                    carried.append((name, hid, data))
            elif (
                "tournament" in name.casefold()
                or "tourney" in name.casefold()
                or _protocol_value([(name, hid, data)], "tournamentId", "tourneyId", "isTournament") is not None
            ):
                # Anything else that marks a tournament still travels, so a
                # capture whose room never sends a join is not read as a ring
                # game. Bounded, and the joins are held apart from it: the
                # lobby sends thousands of standings that identify no table,
                # and they used to push the joins out.
                joins = [event for event in carried if event[0] in TABLE_JOIN_EVENTS]
                rest = [event for event in carried if event[0] not in TABLE_JOIN_EVENTS]
                rest.append((name, hid, data))
                carried[:] = [*joins, *rest[-MAX_SESSION_CONTEXT:]]
            continue
        if hid not in groups:
            order.append(hid)
            # Only this table's join travels with the hand. The others name
            # other tables, and everything that reads the group -- the
            # tournament number, the name, the seat count -- would otherwise
            # find them and answer with another table's tournament.
            table = _table_from_hand_id(hid)
            groups[hid].extend(
                event for event in carried if event[0] not in TABLE_JOIN_EVENTS or _joins_table(event, table)
            )
        groups[hid].append((name, hid, data))

    hands = []
    # A marker that names no table can only be read when there is one table to
    # read it about -- one in the whole capture, not one in this batch.
    #
    # This only ever narrows: a second table having been seen is enough, and
    # its closing does not restore the licence. The marker still names no
    # table, so once two have been played there is no telling which of them it
    # is about -- including one that has since closed, whose last hands may
    # not be imported yet. Recovering the licence would mean reading it as
    # whichever table is open at that moment, which is the guess this is here
    # to prevent.
    tables = session_tables if session_tables is not None else set()
    tables.update(_table_from_hand_id(hid) for hid in order)
    sole_table = len(tables) == 1
    for hid in order:
        note_deal_order(groups[hid], _table_from_hand_id(hid), hid, shape)
        built = _build_one(hid, groups[hid], table_category, sole_table=sole_table, aof=aof, shape=shape)
        if built:
            hands.append(built)
    return hands


def _collect_players(evs: list[tuple]) -> dict[str, dict]:
    """Return {name: {seat, stack}}, stack = chips before the player acted.

    Each seat maps to exactly one player: if a seat changes occupants within the
    captured window (a player leaves, another sits down), the first occupant seen
    wins, so fpdb never receives two players in the same seat.
    """
    players: dict[str, dict] = {}
    used_seats: set = set()

    def note(entry: dict) -> None:
        name = entry.get("userName")
        seat = entry.get("seatId")
        if not name or name in players or seat is None or seat in used_seats:
            return
        chips = Decimal(str(entry.get("userChips", 0) or 0))
        bet = Decimal(str(entry.get("betAmout", 0) or 0))
        players[name] = {"seat": seat, "stack": chips + bet}
        used_seats.add(seat)

    info = _first(evs, "game.seatInfo")
    if info:
        for s in info.get("seatResponseDataList", []) or []:
            note(s)
    for name, _h, d in evs:
        if name in ("game.seat", "game.seatInfo") and isinstance(d, dict):
            if name == "game.seatInfo":
                for s in d.get("seatResponseDataList", []) or []:
                    note(s)
            else:
                note(d)
    return players


def _hero_hole_count(evs: list[tuple]) -> int:
    """Number of cards dealt to the hero, or 0 if they weren't captured."""
    for name in ("game.hole_cards", "game.player_info"):
        ev = _first(evs, name)
        if isinstance(ev, dict):
            cards = ev.get("holeCards") or ev.get("playerCards")
            if cards:
                return len(cards)
    return 0


def _all_dealt_cards(evs: list[tuple]) -> list[dict]:
    """Every card visible in the hand: the hero's hole cards plus the board."""
    hole = _first(evs, "game.hole_cards")
    cards = list(hole.get("holeCards") or []) if isinstance(hole, dict) else []
    for name, _h, d in evs:
        if name == "game.dealer_cards" and isinstance(d, dict):
            for street_cards in (d.get("dealerCards") or {}).values():
                cards.extend(street_cards or [])
    return [c for c in cards if isinstance(c, dict)]


def _detect_category(evs: list[tuple], table_category: str) -> tuple[str, str]:
    """Pick (base, category) from the hand itself, else the GUI hint.

    The hero's hole-card count identifies the Omaha family unambiguously (4/5/6),
    so it wins. Hold'em and short-deck both deal two cards, so the count can't
    tell them apart: trust the session hint, but a 2-5 rank anywhere proves a full
    deck and rules out short-deck even under a wrong hint. The ``table_category``
    dropdown is the fallback when the hero's cards aren't captured (e.g. observing).
    """
    count = _hero_hole_count(evs)
    if count in _HOLE_COUNT_CATEGORY:
        return _HOLE_COUNT_CATEGORY[count]
    if count == 2:
        _, hinted = _CATEGORY.get(table_category.upper(), ("hold", "holdem"))
        low_card_seen = any(c.get("value") in _LOW_RANKS for c in _all_dealt_cards(evs))
        if hinted == "6_holdem" and not low_card_seen:
            return ("hold", "6_holdem")
        return ("hold", "holdem")
    return _CATEGORY.get(table_category.upper(), ("hold", "omahahi"))


# fpdb's own name for All-in or Fold Omaha. It models the game properly: the
# streets are BLINDSANTES/FLOP/TURN/RIVER, with the hole cards on the flop and
# no preflop round at all.
AOF_OMAHA_CATEGORY = "aof_omaha"
AOF_HOLDEM_CATEGORY = "aof_holdem"


def _aof_category(
    category: str,
    table_id: str,
    tables: dict[str, Any],
    shape: dict[str, Any] | None = None,
) -> tuple[str, bool]:
    """Name the All-in or Fold variant of `category`, and say if fpdb has one.

    fpdb models one All-in or Fold game, Omaha. Every other variant the room
    deals -- Hold'em is the one seen -- has no category, and the choice is
    between calling it the ordinary game of the same shape or declaring it
    unsupported.

    It is declared unsupported. Called ordinary Hold'em it would be counted as
    hands played normally, which is the mixing this exists to stop, and it is
    not even reliably that: the variant is read from the room precisely
    because the hand may not say, so a hand with no hole cards captured falls
    back to whatever the GUI is set to and an All-in or Fold Hold'em hand can
    come out as Omaha. Declaring it keeps it out of the statistics and leaves
    a reason on the record; the raw archive keeps the hand itself, so nothing
    is lost that fpdb could not read anyway.
    """
    if table_id not in tables:
        # Nothing named this table. The deal order is the last thing left, and
        # it only answers for a game whose shape fpdb can store.
        if shape is not None and looks_like_all_in_or_fold(table_id, shape):
            if "omaha" in category:
                log.info(
                    "Table %s deals its flop before the betting on %d of %d hands; "
                    "reading it as All-in or Fold Omaha, since neither a join nor the lobby catalogue was captured.",
                    table_id,
                    shape[table_id][0],
                    sum(shape[table_id][:2]),
                )
                return AOF_OMAHA_CATEGORY, True
            if "holdem" in category:
                log.info(
                    "Table %s deals its flop before the betting on %d of %d hands; "
                    "reading it as All-in or Fold Hold'em, since neither a join nor the lobby catalogue was captured.",
                    table_id,
                    shape[table_id][0],
                    sum(shape[table_id][:2]),
                )
                return AOF_HOLDEM_CATEGORY, True
        return category, True
    if tables[table_id] == MINI_GAME_OMAHA:
        return AOF_OMAHA_CATEGORY, True
    if tables[table_id] == MINI_GAME_HOLDEM:
        return AOF_HOLDEM_CATEGORY, True
    log.info(
        "Table %s deals All-in or Fold, which fpdb models only for Omaha and Hold'em; "
        "its hands are kept in the raw archive rather than stored as %s.",
        table_id,
        category,
    )
    return category, False


def _move_preflop_to_flop(actions: list[dict]) -> None:
    """Put All-in or Fold action on the street the game actually has.

    The room deals the flop before anyone acts and names the round on every
    action: across seventy-eight captured hands of it, no action was ever
    labelled preflop. So this is not about how the hand was played -- it is
    about how much of it was captured. An action arriving without its round
    keeps the street the reader started on, which is preflop, and preflop is a
    street fpdb's model of this game does not have: the hand then raises on
    the first action written and is not imported at all. A capture begun
    mid-hand, or one lost packet, is all it takes. The first betting round is
    the flop either way.
    """
    for action in actions:
        if action.get("street") == "PREFLOP":
            action["street"] = "FLOP"


def _hand_start_time(info: dict) -> datetime.datetime | None:
    """Convert the event's initTimeStamp (epoch ms) to a UTC-naive datetime.

    Preferring the protocol's own clock over the import wall-clock keeps replayed
    or backlogged captures on their real dates in the GUI graphs/filters.
    """
    raw = info.get("initTimeStamp")
    if raw is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(int(raw) / 1000, tz=datetime.UTC).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _board_from_dealer(dealer: dict) -> dict[str, list[str]]:
    """Turn a ``dealerCards`` street->cards map into a capped board dict."""
    board: dict[str, list[str]] = {}
    for street in ("FLOP", "TURN", "RIVER"):
        if dealer.get(street):
            board[street] = _cards(dealer[street])[: _STREET_LEN[street]]
    return board


def _extract_boards(evs: list[tuple]) -> tuple[list[dict[str, list[str]]], int, bool]:
    """Return ``(boards, run_it_times, double_board)`` from the dealer snapshots.

    ``boards[0]`` is the primary run. Run-it-twice adds ``dealerCardsRit`` /
    ``dealerCardsRit2`` boards, which share the primary flop (only the turn/river
    are re-dealt after an all-in). A bomb pot's ``dealerCardsDoubleBoard`` is an
    independent second board dealt from its own flop. ``run_it_times`` counts the
    RIT runs only (1 when not run multiple times); a double board is not RIT.
    """
    primary: dict[str, list[str]] = {}
    rit1: dict[str, list[str]] = {}
    rit2: dict[str, list[str]] = {}
    dbl: dict[str, list[str]] = {}
    for name, _h, d in evs:
        if name != "game.dealer_cards" or not isinstance(d, dict):
            continue
        if d.get("dealerCards"):
            primary = _board_from_dealer(d["dealerCards"])
        if d.get("dealerCardsRit"):
            rit1 = _board_from_dealer(d["dealerCardsRit"])
        if d.get("dealerCardsRit2"):
            rit2 = _board_from_dealer(d["dealerCardsRit2"])
        if d.get("dealerCardsDoubleBoard"):
            dbl = _board_from_dealer(d["dealerCardsDoubleBoard"])

    win = _first(evs, "game.winnerInfo") or {}
    rit_flag = bool(win.get("rit")) or bool(rit1) or bool(rit2)
    double_flag = bool(win.get("doubleBoard")) or bool(dbl)

    boards: list[dict[str, list[str]]] = [primary] if primary else []
    for run in (rit1, rit2):
        if run:
            merged = dict(run)
            if not merged.get("FLOP") and primary.get("FLOP"):
                merged["FLOP"] = list(primary["FLOP"])  # RIT runs share the flop
            boards.append(merged)
    if dbl:
        boards.append(dbl)

    run_it_times = len([b for b in (primary, rit1, rit2) if b]) if rit_flag else 1
    return boards, run_it_times, double_flag


def _extract_splash(evs: list[tuple]) -> tuple[int, bool]:
    """Return ``(splash_pot_cents, is_mega_splash)`` from cumulativeWinnerInfo."""
    cum = _first(evs, "game.cumulativeWinnerInfo") or {}
    try:
        amount = int(round(float(cum.get("splashPotAmount", 0) or 0) * 100))
    except (TypeError, ValueError):
        amount = 0
    return amount, bool(cum.get("isMegaSplash"))


EV_CASHOUT_EVENT = "game.ev_chop_opted_action"


def _ev_cashout_accepted(evs: list[tuple]) -> bool:
    """True when a player took the EV cashout offered on this hand.

    Their equity is bought out instead of played, which moves money outside
    both the pot and the splash. It is the one settlement shape whose figures
    could not be reproduced from the room's own account, so a hand carrying it
    is left alone rather than credited on a rule that does not describe it.
    """
    for name, _hid, data in evs:
        if name != EV_CASHOUT_EVENT or not isinstance(data, dict):
            continue
        for opted in data.get("optedEvChopActionData") or []:
            if isinstance(opted, dict) and opted.get("optedForEVChop"):
                return True
    return False


def _extract_splash_winnings(evs: list[tuple]) -> list[dict[str, str]]:
    """Return the splash paid to each player, beside the pot rather than in it.

    The room drops this money on the table and pays it to whoever it marks
    ``isSplashPotWinner``, crediting their stack directly: it never appears in
    a pot event, and a hand's winner can end up with more than the pot held.
    It is shared in proportion to what each of them took from the settlement --
    pot winnings and insurance payouts alike, since a player paid only through
    insurance is marked too and would otherwise receive nothing.

    Verified against the room's own ``cumulativeProfitLoss`` on 33 of the 35
    settled results in the captures; the two it cannot account for are the one
    hand where an EV cashout was accepted, which is excluded here.
    """
    cumulative = _first(evs, "game.cumulativeWinnerInfo")
    if not cumulative or _ev_cashout_accepted(evs):
        return []
    splash = _decimal_or_none(cumulative.get("splashPotAmount")) or Decimal(0)
    marked = [
        winner.get("userName")
        for winner in cumulative.get("winnersData") or []
        if winner.get("isSplashPotWinner") and winner.get("userName")
    ]
    if splash <= 0 or not marked:
        return []

    taken: dict[str, Decimal] = defaultdict(Decimal)
    for entry in _extract_collections(evs):
        taken[entry["player"]] += Decimal(entry["pot"])
    for entry in _extract_cashout(evs):
        taken[entry["player"]] += Decimal(entry["amount"])
    total = sum(taken.get(player, Decimal(0)) for player in marked)
    if total <= 0:
        return []

    return [
        {
            "player": player,
            "amount": str((splash * taken.get(player, Decimal(0)) / total).quantize(Decimal("0.01"))),
        }
        for player in marked
    ]


def _extract_cashout(evs: list[tuple]) -> list[dict[str, str]]:
    """Return per-player EV cashout (insurance) entries from winnerInfo.

    A winner who took insurance is flagged ``isInsured``: ``actualWinAmount`` is
    what they were actually paid, ``winAmountFromPot`` what the pot owed them, so
    the difference is the insurance fee they gave up.
    """
    cashout: list[dict[str, str]] = []
    seen: set[tuple] = set()
    # Same rule as the pot collections: a repeated envelope inside one
    # settlement is the room saying the same thing twice, while the same
    # amount in a later settlement is another board. A player insured across a
    # side pot is paid once per pot, and every one of those payouts counts.
    settlements = [data for name, _hid, data in evs if name == "game.winnerInfo" and isinstance(data, dict)]
    for index, d in enumerate(settlements):
        for w in d.get("winnerDataList", []) or []:
            for det in (w.get("winnerDetails") or {}).get("winnerList") or []:
                if not det.get("isInsured"):
                    continue
                player = det.get("playerName")
                if not player:
                    continue
                paid = _decimal_or_none(det.get("actualWinAmount"))
                pot = _decimal_or_none(det.get("winAmountFromPot"))
                if paid is None:
                    continue
                # Some insured results omit the theoretical pot entitlement.
                # Keep the exact payout and leave the unknown fee at zero.
                if pot is None:
                    pot = paid
                fee = pot - paid
                key = (index, w.get("potId"), player, paid, pot)
                if key in seen:
                    continue
                seen.add(key)
                cashout.append(
                    {
                        "player": player,
                        "amount": str(paid),
                        "fee": str(fee if fee > 0 else Decimal(0)),
                    }
                )
    return cashout


def _extract_collections(evs: list[tuple]) -> list[dict[str, str]]:
    """Return poker-pot collections, excluding separate insurance payouts."""
    collections: list[dict[str, str]] = []
    seen: set[tuple] = set()
    # Every settlement, not just the first. A hand run twice settles once per
    # board, and reading only the first paid the winner half of what they
    # actually took -- 0.34 instead of 0.68 on one captured hand, 3.18 instead
    # of 6.35 on another.
    settlements = [data for name, _hid, data in evs if name == "game.winnerInfo" and isinstance(data, dict)]
    for index, win in enumerate(settlements):
        for winner in win.get("winnerDataList", []) or []:
            winner_list = (winner.get("winnerDetails") or {}).get("winnerList") or []
            for detail in winner_list:
                # EV cashout/insurance is external to the poker pot and is
                # stored in HandsCashout. Adding it here inflates winnings and
                # can count the same payout once per winner snapshot.
                if detail.get("isInsured"):
                    continue
                player = detail.get("playerName")
                amount = _decimal_or_none(detail.get("winAmountFromPot"))
                if amount is None:
                    amount = _decimal_or_none(winner.get("potAmountAfterRake"))
                if not player or amount is None:
                    continue
                # Repeated envelopes inside one settlement are the room saying
                # the same thing twice; the same amount in a *later*
                # settlement is a different board, and must be kept.
                key = (index, winner.get("potId"), player, amount)
                if key not in seen:
                    seen.add(key)
                    collections.append({"player": player, "pot": str(amount)})
    if collections:
        return collections

    cumulative = _first(evs, "game.cumulativeWinnerInfo")
    if cumulative:
        for winner in cumulative.get("winnersData", []) or []:
            player = winner.get("userName")
            amount = _decimal_or_none(winner.get("amount", winner.get("winAmount")))
            if player and amount is not None:
                collections.append({"player": player, "pot": str(amount)})
    return collections


def _post_blind(actions: list[dict], posted: set[tuple[str, str]], player: str, kind: str, amount: Decimal) -> bool:
    """Record a blind the first time it is seen, and say whether it was new."""
    if (player, kind) in posted:
        return False
    posted.add((player, kind))
    actions.append({"type": kind, "player": player, "amount": str(amount)})
    return True


SHOWDOWN_CARD_EVENTS = ("game.show_hole_cards", "game.reveal_cards")


def _add_revealed_holecards(evs: list[tuple], holecards: list[dict], seat2name: dict) -> None:
    """Record the hands the room turned face up at showdown.

    Only the hero's own cards arrive as ``game.hole_cards``; everyone else's
    come at showdown, keyed by seat, in ``userCardListMap``. Reading only the
    first meant no opponent ever had a holding on record -- across six hundred
    captured hands, the hero's cards were known in every one of them and no
    other player's in any, so every read that rests on what someone shows up
    with was empty for exactly the people it is meant to describe.
    """
    known = {entry["player"] for entry in holecards}
    for name, _hid, data in evs:
        if name not in SHOWDOWN_CARD_EVENTS or not isinstance(data, dict):
            continue
        for seat, cards in (data.get("userCardListMap") or {}).items():
            player = _seat_player(seat, seat2name)
            if not player or player in known or not cards:
                continue
            known.add(player)
            holecards.append(
                {
                    "player": player,
                    "closed": _cards(cards),
                    "dealt": True,
                    "shown": True,
                    "mucked": False,
                },
            )


def _seat_player(seat: Any, seat2name: dict) -> str | None:
    """The player sitting in this seat, whichever way the room spells it."""
    try:
        return seat2name.get(int(seat))
    except (TypeError, ValueError):
        return None


def _explicit_betting_actions(
    evs: list[tuple],
    *,
    sb: Decimal,
    bb: Decimal,
    sb_name: str | None,
    bb_name: str | None,
    is_aof: bool = False,
) -> list[dict] | None:
    """Translate CoinPoker's authoritative dealer action stream when present."""
    records: list[dict] = []
    seen: set[tuple] = set()
    for name, _hid, payload in evs:
        if name != "game.dealer_chat_action" or not isinstance(payload, dict):
            continue
        for record in payload.get("gameActionMessagesHistory") or []:
            if not isinstance(record, dict):
                continue
            key = (
                record.get("initTimestamp"),
                record.get("username"),
                record.get("action"),
                record.get("roundName"),
                record.get("actionAmount"),
            )
            if key not in seen:
                seen.add(key)
                records.append(record)
    if not records:
        return None

    actions: list[dict] = []
    committed: dict[str, Decimal] = {}
    if sb_name:
        committed[sb_name] = sb
    if bb_name:
        committed[bb_name] = bb
    street_to = bb
    street = "PREFLOP"
    # A blind is posted once, however many times the room repeats the seat
    # snapshot that mentions it. Repeating it put the big blind in the hand
    # twice and, because posting a blind is handled before the street can
    # change, carried the second one onto the next street as money already in.
    posted: set[tuple[str, str]] = set()
    blinds: dict[str, Decimal] = {}
    opened = False
    for record in records:
        player = record.get("username")
        raw_action = str(record.get("action") or "").upper()
        action = str(record.get("newPlayerAction") or raw_action).upper()
        round_name = str(record.get("roundName") or "").upper()
        amount = Decimal(str(record.get("actionAmount", 0) or 0))
        if not player or not action:
            continue
        if action == "ANTE":
            actions.append({"type": "ante", "player": player, "amount": str(amount)})
            continue
        if action == "SB":
            if _post_blind(actions, posted, player, "small blind", amount):
                committed[player] = blinds[player] = amount
            continue
        if action == "BB":
            if _post_blind(actions, posted, player, "big blind", amount):
                committed[player] = blinds[player] = amount
                street_to = amount
            continue
        if action == "STRADDLE":
            actions.append({"type": "straddle", "player": player, "amount": str(amount)})
            committed[player] = amount
            street_to = max(street_to, amount)
            continue
        if round_name in {"PREFLOP", "FLOP", "TURN", "RIVER"} and round_name != street:
            first_betting_street = not opened
            street = round_name
            opened = True
            # In All-in or Fold the blinds are live money on the flop: the
            # game has no preflop round of its own, so the round they were
            # posted into *is* the one that is bet. Clearing them there
            # charged the blind twice -- once when posted and again inside the
            # shove total -- which left the stack negative and so never
            # exactly zero, which is what marks an action all-in.
            #
            # Only in that game. Every other one has its own preflop round, so
            # a capture of it that began at the flop must not carry blinds
            # from a round that finished before the recording started.
            committed.clear()
            if first_betting_street and is_aof:
                committed.update(blinds)
                street_to = max(blinds.values(), default=Decimal(0))
            else:
                street_to = Decimal(0)
        if action == "FOLD":
            actions.append({"type": "folds", "player": player, "street": street})
        elif action == "CHECK":
            actions.append({"type": "checks", "player": player, "street": street})
        elif action == "CALL":
            # On a call betAmout is what this action adds, which is what
            # Hand.py wants -- unlike the all-in record below, where it is the
            # player's whole commitment. The two are not spelled differently;
            # only the data says so.
            actions.append({"type": "calls", "player": player, "street": street, "amount": str(amount)})
            committed[player] = committed.get(player, Decimal(0)) + amount
        elif raw_action == "RAISE":
            if action == "BET" or not street_to:
                actions.append({"type": "bets", "player": player, "street": street, "amount": str(amount)})
            else:
                actions.append({"type": "raises", "player": player, "street": street, "to": str(amount)})
            committed[player] = amount
            street_to = amount
        elif action in {"ALLIN", "ALL_IN"} or raw_action in {"ALLIN", "ALL_IN"}:
            # betAmout is what the player has put in altogether, not what this
            # action adds -- which is how the raise branch beside this one
            # already reads it. Adding the blind on top made a player who had
            # posted one raise to more than they owned: an All-in or Fold hero
            # with a 2.00 stack came out raising to 2.25, and the stack that
            # followed it went negative.
            total = max(amount, committed.get(player, Decimal(0)))
            if total <= street_to:
                put_in = max(total - committed.get(player, Decimal(0)), Decimal(0))
                actions.append({"type": "calls", "player": player, "street": street, "amount": str(put_in)})
            elif street_to:
                actions.append({"type": "raises", "player": player, "street": street, "to": str(total)})
                street_to = total
            else:
                actions.append({"type": "bets", "player": player, "street": street, "amount": str(amount)})
                street_to = total
            committed[player] = total
    return actions


def _build_one(
    hid: str,
    evs: list[tuple],
    table_category: str,
    *,
    sole_table: bool = True,
    aof: dict[str, Any] | None = None,
    shape: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    info = _first(evs, "game.pre_hand_start_info")
    if not info:
        return None

    base, category = _detect_category(evs, table_category)
    # The table is worked out first: it is what tells a tournament's hands from
    # those of every other table the capture is carrying.
    table_id = str(info.get("tableId") or _table_from_hand_id(hid))
    category, fpdb_supported = _aof_category(
        category,
        table_id,
        aof if aof is not None else aof_tables(evs),
        shape,
    )
    tournament = _tournament_info(evs, table_id, sole_table=sole_table)
    if tournament:
        joined = joined_tournaments(evs).get(table_id)
        if joined:
            tournament["tour_no"], joined_name = joined[0], joined[1]
            tournament["name"] = joined_name or tournament.get("name")
    sb = Decimal(str(info.get("sbAmount", 0)))
    bb = Decimal(str(info.get("bbAmount", 0)))
    ante = Decimal(str(info.get("anteAmount", 0)))

    players = _collect_players(evs)
    seat2name = {p["seat"]: n for n, p in players.items()}

    actions: list[dict] = []
    # Blinds first (addBlind ignores street).
    if info.get("anteAmount"):
        for nm in players:
            if ante > 0:
                actions.append({"type": "ante", "player": nm, "amount": str(ante)})
    sb_name = seat2name.get(info.get("sbSeatId"))
    bb_name = seat2name.get(info.get("bbSeatId"))
    if sb_name:
        actions.append({"type": "small blind", "player": sb_name, "amount": str(sb)})
    if bb_name:
        actions.append({"type": "big blind", "player": bb_name, "amount": str(bb)})

    # Boards from the last cumulative dealer_cards snapshot. ``boards[0]`` is the
    # primary run, kept as ``community`` so single-board hands are unchanged; the
    # full list carries run-it-twice runs and bomb-pot double boards.
    boards, run_it_times, double_board = _extract_boards(evs)
    community: dict[str, list[str]] = dict(boards[0]) if boards else {}

    # Hero hole cards.
    holecards: list[dict] = []
    hero = None
    for name, _h, d in evs:
        if name == "game.dealer_chat" and isinstance(d, dict):
            m = re.match(r"^(?P<p>.+?) My Hole Cards ", d.get("dealerMessage", ""))
            if m:
                hero = m.group("p")
    hole = _first(evs, "game.hole_cards")
    if hero and hole and hole.get("holeCards"):
        holecards.append(
            {
                "player": hero,
                "closed": _cards(hole["holeCards"]),
                "dealt": True,
                "shown": False,
                "mucked": False,
            }
        )

    _add_revealed_holecards(evs, holecards, seat2name)

    explicit_actions = _explicit_betting_actions(
        evs,
        sb=sb,
        bb=bb,
        sb_name=sb_name,
        bb_name=bb_name,
        is_aof=category in (AOF_OMAHA_CATEGORY, AOF_HOLDEM_CATEGORY),
    )
    if explicit_actions is not None:
        # This stream also identifies exactly who posted antes/blinds, avoiding
        # forced bets for seated players who are sitting out.
        actions = explicit_actions

    # Otherwise reconstruct actions from game.seat events (interleaved with the dealer-chat
    # street markers). betAmout is the player's authoritative total commitment on
    # the current street, which reconciles pot math for every action type,
    # including all-ins and side pots, unlike parsing the chat narrative.
    street = "PREFLOP"
    street_has_bet = {"PREFLOP": True, "FLOP": False, "TURN": False, "RIVER": False}
    street_to = {"PREFLOP": ante + bb, "FLOP": Decimal(0), "TURN": Decimal(0), "RIVER": Decimal(0)}
    # CoinPoker includes the ante in ``betAmout`` snapshots.  Seed it here so
    # the post-ante seat refresh (whose stale caption is commonly ``Raise``)
    # is not imported as a zero/negative raise.
    committed: dict[str, Decimal] = {name: ante for name in players}  # player -> chips already in this street snapshot
    if sb_name:
        committed[sb_name] += sb
    if bb_name:
        committed[bb_name] += bb
    non_actions = {None, "", "Inuse", "SB", "BB", "Waiting", "SitOut", "Muck"}
    for name, _h, d in evs if explicit_actions is None else ():
        if not isinstance(d, dict):
            continue
        if name == "game.dealer_chat":
            msg = (d.get("dealerMessage") or "").strip()
            if msg == "PREFLOP":
                street = "PREFLOP"
            else:
                m = re.match(r"^(FLOP|TURN|RIVER) \[", msg)
                if m:
                    street = m.group(1)
                    committed.clear()  # new street: reset per-street commitments
            continue
        if name != "game.seat":
            continue
        # Use caption (current state) not lastAction: end-of-hand/return-chips
        # updates keep a stale lastAction like "Raise" while caption is "Inuse".
        action = d.get("caption")
        player = d.get("userName")
        if not player or action in non_actions:
            continue
        bet = Decimal(str(d.get("betAmout", 0) or 0))
        if action == "Straddle":
            if bet <= committed.get(player, Decimal(0)):
                continue
            actions.append({"type": "straddle", "player": player, "amount": str(bet)})
            committed[player] = bet
            street_has_bet["PREFLOP"] = True
            street_to["PREFLOP"] = max(street_to["PREFLOP"], bet)
        elif action == "Fold":
            actions.append({"type": "folds", "player": player, "street": street})
        elif action == "Check":
            actions.append({"type": "checks", "player": player, "street": street})
        elif action == "Call":
            amount = bet - committed.get(player, Decimal(0))
            if amount <= 0:
                continue
            actions.append({"type": "calls", "player": player, "street": street, "amount": str(amount)})
            committed[player] = bet
        else:  # Raise / Bet / Pot / Allin / Straddle -> aggressive: bet to `bet`
            if bet <= committed.get(player, Decimal(0)):
                continue
            # ``Allin`` describes the player's state, not necessarily an
            # aggressive action.  At or below the current price it is a call
            # (possibly a short all-in), not a zero-sized raise.
            if bet <= street_to[street]:
                amount = bet - committed.get(player, Decimal(0))
                actions.append({"type": "calls", "player": player, "street": street, "amount": str(amount)})
                committed[player] = bet
                continue
            if street_has_bet[street]:
                actions.append({"type": "raises", "player": player, "street": street, "to": str(bet)})
            else:
                actions.append({"type": "bets", "player": player, "street": street, "amount": str(bet)})
            street_has_bet[street] = True
            street_to[street] = bet
            committed[player] = bet

    # Winners -> collections (use post-rake amount actually paid out).
    collections = _extract_collections(evs)

    players_list = [
        {"seat_idx": p["seat"], "name": n, "starting_stack": str(p["stack"])}
        for n, p in sorted(players.items(), key=lambda kv: kv[1]["seat"] or 0)
    ]

    # Bomb pot: every player is forced to ante and the deal jumps straight to a
    # (typically double) board. CoinPoker's bomb pots are always dealt two boards,
    # so an ante paired with a double board is the reliable signal. The stored
    # amount is the total forced antes, in cents.
    if category in (AOF_OMAHA_CATEGORY, AOF_HOLDEM_CATEGORY):
        _move_preflop_to_flop(actions)

    splash_pot, mega_splash = _extract_splash(evs)
    cashout = _extract_cashout(evs)
    bomb_pot = int(ante * 100 * len(players)) if ante > 0 and double_board else 0

    # The table id is the hand id without its trailing 5-digit hand counter
    # (gameId 91426500343 -> table 914265), which also matches the number shown
    # in the CoinPoker window title ("PLO4 914265 ..."). This gives each table a
    # distinct, stable name so the HUD creates one window per table.
    if tournament and tournament.get("tour_no") is None:
        # CoinPoker's MTT hand stream identifies itself by transport port but
        # does not always repeat lobby metadata inside each hand.  The table
        # prefix is stable for the captured table and keeps the hand on FPDB's
        # tournament path instead of silently storing tournament chips as USD.
        tournament["tour_no"] = table_id
        log.warning(
            "No tournament number for hand %s; naming it after table %s. "
            "The HUD identity changes if the player is moved.",
            hid,
            table_id,
        )
    if tournament and tournament.get("table_id") is None:
        tournament["table_id"] = table_id
    if tournament and tournament.get("name") is None:
        tournament["name"] = f"CoinPoker MTT {tournament['tour_no']}"
    stored_table_id = f"{tournament['tour_no']} {table_id}" if tournament else table_id

    max_seats = (tournament or {}).get("max_seats")
    if max_seats is None:
        configured_max = next(
            (
                seats
                for field in ("maxSeats", "tableSize")
                if (seats := _seat_count(info.get(field), source=f"the table's {field}")) is not None
            ),
            None,
        )
        if configured_max is not None:
            max_seats = configured_max
        else:
            max_seats = max(len(players), MIN_TABLE_SEATS) if tournament else 6
    game_type = "tour" if tournament else "ring"

    return {
        "site": "CoinPoker",
        "hand_id": str(hid),
        "hero": hero,
        "table_id": stored_table_id,
        "timestamp": _hand_start_time(info),
        "buttonpos": info.get("dealerSeatId"),
        "game": {"base": base, "category": category, "fpdb_supported": fpdb_supported},
        # All-in or Fold deals the flop before anyone acts, so that is where
        # the cards belong and where fpdb looks for them. Left on PREFLOP --
        # a street this game does not have -- the hole cards are attached to
        # nothing the hand will ever read.
        **({"streets": {"holeStreets": ["FLOP"]}} if category in (AOF_OMAHA_CATEGORY, AOF_HOLDEM_CATEGORY) else {}),
        "gametype": {
            "base": base,
            "category": category,
            "type": game_type,
            "limitType": "pl" if base == "hold" and "omaha" in category else "nl",
            "currency": "T$" if tournament else "USD",
            "sb": str(sb),
            "bb": str(bb),
            "ante": str(ante),
            "maxSeats": max_seats,
        },
        "tournament": tournament,
        "players": players_list,
        "actions": actions,
        "community": community,
        "boards": boards,
        "run_it_times": run_it_times,
        "double_board": double_board,
        "bomb_pot": bomb_pot,
        "splash_pot": splash_pot,
        "mega_splash": mega_splash,
        "cashout": cashout,
        "splash_winnings": _extract_splash_winnings(evs),
        "holecards": holecards,
        "collections": collections,
    }
