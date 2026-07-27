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

# How many other tournament markers travel alongside the joins.
MAX_SESSION_CONTEXT = 100


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
    return _protocol_value([event for event in evs if event[0] != TOURNAMENT_JOIN_EVENT], *keys)


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
    """True when this carried event is the join of `table`."""
    return event[0] == TOURNAMENT_JOIN_EVENT and _table_from_title((event[2] or {}).get("tableName")) == table


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
) -> list[dict[str, Any]]:
    """Group decoded events by hand id and build a normalized dict per hand.

    ``session_context`` carries the tournament announcements across calls. The
    room announces the tournament once, when the table is joined, so a batch
    arriving later has nothing identifying it -- and a hand with no tournament
    number falls back to naming itself after its table, which changes the
    moment the player is moved. Two HUDs for one tournament is what that looks
    like. Pass the same list on every call to keep the announcement.

    ``session_tables`` remembers the tables this capture has dealt hands at.
    Whether a marker naming no table is ambiguous is a fact about the capture,
    not about the twenty events in hand: a sweep holding a single hand looks
    unambiguous however many tables are being played, and that is most sweeps.
    Pass the same set on every call.
    """
    order: list[str] = []
    groups: dict[str, list[tuple]] = defaultdict(list)
    carried: list[tuple] = session_context if session_context is not None else []
    for name, hid, data in events:
        if hid is None:
            # Attached to the hand in progress so a late announcement still
            # reaches it -- unless it is another table's join, which would tell
            # that hand it belongs to a tournament it has never been in.
            if order and (
                name != TOURNAMENT_JOIN_EVENT or _joins_table((name, hid, data), _table_from_hand_id(order[-1]))
            ):
                groups[order[-1]].append((name, hid, data))
            if name == TOURNAMENT_JOIN_EVENT:
                # One join is kept per table, and never evicted. Keeping them
                # all is what lets a player sit at several tournaments at once,
                # and keeping only the newest would strand the tables joined
                # before it; they are told apart by table, so none can claim
                # another's hands.
                table = _table_from_title((data or {}).get("tableName"))
                if table:
                    carried[:] = [event for event in carried if not _joins_table(event, table)]
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
                joins = [event for event in carried if event[0] == TOURNAMENT_JOIN_EVENT]
                rest = [event for event in carried if event[0] != TOURNAMENT_JOIN_EVENT]
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
                event for event in carried if event[0] != TOURNAMENT_JOIN_EVENT or _joins_table(event, table)
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
        built = _build_one(hid, groups[hid], table_category, sole_table=sole_table)
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


def _hand_start_time(info: dict) -> datetime.datetime | None:
    """Convert the event's initTimeStamp (epoch ms) to a UTC-naive datetime.

    Preferring the protocol's own clock over the import wall-clock keeps replayed
    or backlogged captures on their real dates in the GUI graphs/filters.
    """
    raw = info.get("initTimeStamp")
    if raw is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(int(raw) / 1000, tz=datetime.timezone.utc).replace(tzinfo=None)
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


def _extract_cashout(evs: list[tuple]) -> list[dict[str, str]]:
    """Return per-player EV cashout (insurance) entries from winnerInfo.

    A winner who took insurance is flagged ``isInsured``: ``actualWinAmount`` is
    what they were actually paid, ``winAmountFromPot`` what the pot owed them, so
    the difference is the insurance fee they gave up.
    """
    cashout: list[dict[str, str]] = []
    for name, _h, d in evs:
        if name != "game.winnerInfo" or not isinstance(d, dict):
            continue
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
    seen: set[tuple[str, Decimal]] = set()
    win = _first(evs, "game.winnerInfo")
    if win:
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
                key = (player, amount) if player and amount is not None else None
                if key is not None and key not in seen:
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


def _explicit_betting_actions(
    evs: list[tuple],
    *,
    sb: Decimal,
    bb: Decimal,
    sb_name: str | None,
    bb_name: str | None,
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
            actions.append({"type": "small blind", "player": player, "amount": str(amount)})
            committed[player] = amount
            continue
        if action == "BB":
            actions.append({"type": "big blind", "player": player, "amount": str(amount)})
            committed[player] = amount
            street_to = amount
            continue
        if action == "STRADDLE":
            actions.append({"type": "straddle", "player": player, "amount": str(amount)})
            committed[player] = amount
            street_to = max(street_to, amount)
            continue
        if round_name in {"PREFLOP", "FLOP", "TURN", "RIVER"} and round_name != street:
            street = round_name
            committed.clear()
            street_to = Decimal(0)
        if action == "FOLD":
            actions.append({"type": "folds", "player": player, "street": street})
        elif action == "CHECK":
            actions.append({"type": "checks", "player": player, "street": street})
        elif action == "CALL":
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
            total = committed.get(player, Decimal(0)) + amount
            if total <= street_to:
                actions.append({"type": "calls", "player": player, "street": street, "amount": str(amount)})
            elif street_to:
                actions.append({"type": "raises", "player": player, "street": street, "to": str(total)})
                street_to = total
            else:
                actions.append({"type": "bets", "player": player, "street": street, "amount": str(amount)})
                street_to = total
            committed[player] = total
    return actions


def _build_one(hid: str, evs: list[tuple], table_category: str, *, sole_table: bool = True) -> dict[str, Any] | None:
    info = _first(evs, "game.pre_hand_start_info")
    if not info:
        return None

    base, category = _detect_category(evs, table_category)
    # The table is worked out first: it is what tells a tournament's hands from
    # those of every other table the capture is carrying.
    table_id = str(info.get("tableId") or _table_from_hand_id(hid))
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

    explicit_actions = _explicit_betting_actions(
        evs,
        sb=sb,
        bb=bb,
        sb_name=sb_name,
        bb_name=bb_name,
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
        "game": {"base": base, "category": category, "fpdb_supported": True},
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
        "holecards": holecards,
        "collections": collections,
    }
