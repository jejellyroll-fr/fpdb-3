"""Rebuild the session tables from the stored hands (#598).

The import groups hands into Sessions, SessionsCache and TourneysCache as it
goes (``storeSessions``, ``storeSessionsCache`` and ``storeTourneysCache``),
merging windows that a later file bridges; nothing could regenerate them. A
repair that deletes hands therefore left their contribution behind, and any
drift stayed for good.

The rebuild empties those tables and replays the same three functions over
every stored hand, in time order and in batches, exactly as an import of the
hands one file per batch would. Reusing the import's grouping, rather than a
second implementation of it in SQL, keeps the two from drifting apart.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from fpdb_3_legacy.database_caches import SESSION_CACHE_KEYS
from fpdb_3_legacy.sql_queries_cache_rebuild import (
    SESSION_REBUILD_ANY_SESSION,
    SESSION_REBUILD_CLEAR,
    SESSION_REBUILD_FIRST_HANDS,
    SESSION_REBUILD_HAND_SESSION,
    SESSION_REBUILD_NEXT_HANDS,
    SESSION_REBUILD_ORPHAN_PERIODS,
    SESSION_REBUILD_PLAYERS,
)

# Hands read and replayed per batch: the import's grouping compares each hand
# with every session of its batch, so one batch for a whole database would be
# quadratic, and would hold every hand in memory. Sessions that run across
# batches are merged through the database, as successive files are.
BATCH = 500

# Keys the import computes rather than reads from HandsPlayers (DerivedStats).
DERIVED_KEYS = ("n", "showdownWinnings", "nonShowdownWinnings")
STORED_KEYS = tuple(key for key in SESSION_CACHE_KEYS if key not in DERIVED_KEYS)

# The import's buffers the replay uses; saved and restored around it.
BUFFERS = ("s", "sc", "tc", "tbulk", "wmold", "wmnew")


def rebuild_sessions(db: Any, *, commit: bool = True, batch: int = BATCH) -> None:
    """Regenerate Sessions, SessionsCache, TourneysCache and the session ids.

    CardsCache and PositionsCache read their week and month through Sessions:
    rebuild them afterwards, then call :func:`delete_orphan_periods`.

    With ``commit=False`` nothing is committed, the import's own commits
    included, so the caller can roll the rebuild back with its other writes.
    """
    saved = {name: getattr(db, name, None) for name in BUFFERS}
    db._in_transaction += 1
    try:
        cursor = db.get_cursor()
        for statement in SESSION_REBUILD_CLEAR:
            cursor.execute(statement)
        players = _players_query(db)
        hands = _first_hands(db, batch)
        while hands:
            _replay(db, hands, players)
            hands = _next_hands(db, hands[-1], batch)
    finally:
        db._in_transaction -= 1
        for name, value in saved.items():
            setattr(db, name, value)
    if commit:
        db.commit()


def has_sessions(db: Any) -> bool:
    """Whether the database holds sessions, which a repair must then rebuild whatever the current setting."""
    cursor = db.get_cursor()
    cursor.execute(SESSION_REBUILD_ANY_SESSION)
    row = cursor.fetchone()
    return row is not None and row[0] is not None


def delete_orphan_periods(db: Any) -> None:
    """Remove the weeks and months nothing points at any more; does not commit."""
    cursor = db.get_cursor()
    for statement in SESSION_REBUILD_ORPHAN_PERIODS:
        cursor.execute(statement)


def _first_hands(db: Any, batch: int) -> list[Any]:
    cursor = db.get_cursor()
    cursor.execute(SESSION_REBUILD_FIRST_HANDS.replace("%s", db.sql.query["placeholder"]), (batch,))
    return cursor.fetchall()


def _next_hands(db: Any, last: Sequence[Any], batch: int) -> list[Any]:
    """The batch after ``last``, in (startTime, id) order."""
    cursor = db.get_cursor()
    cursor.execute(
        SESSION_REBUILD_NEXT_HANDS.replace("%s", db.sql.query["placeholder"]), (last[1], last[1], last[0], batch)
    )
    return cursor.fetchall()


def _players_query(db: Any) -> str:
    columns = "".join(", hp." + key for key in STORED_KEYS)
    return SESSION_REBUILD_PLAYERS.replace("<columns>", columns)


def _replay(db: Any, hands: Sequence[Sequence[Any]], players: str) -> None:
    """Feed one batch of hands to the import's session functions, then store it."""
    db.s, db.sc, db.tc, db.tbulk = {"bk": []}, {}, {}, {}
    db.wmold, db.wmnew = set(), set()
    pdata = _player_rows(db, [hand[0] for hand in hands], players)
    last = len(hands) - 1
    for i, (hid, start_time, tourney_id, gametype_id, game_type) in enumerate(hands):
        rows = pdata.get(hid, {})
        pids = {player: player for player in rows}
        heroes = [next(iter(pids.values()))] if pids else []
        doinsert = i == last
        db.storeSessions(hid, pids, start_time, tourney_id, heroes, None, doinsert)
        db.storeSessionsCache(hid, pids, start_time, gametype_id, None, rows, heroes, doinsert)
        db.storeTourneysCache(hid, pids, start_time, tourney_id, {"type": game_type}, rows, heroes, doinsert)
    _store_session_ids(db, hands)


def _player_rows(db: Any, hand_ids: list[Any], players: str) -> dict[Any, dict[Any, dict[str, Any]]]:
    """Each hand's players, keyed by player id, with the values the import stores."""
    placeholder = db.sql.query["placeholder"]
    query = players.replace("<hand_ids>", ", ".join([placeholder] * len(hand_ids)))
    cursor = db.get_cursor()
    cursor.execute(query, hand_ids)
    rows: dict[Any, dict[Any, dict[str, Any]]] = defaultdict(dict)
    for hid, pid, saw_showdown, total_profit, *values in cursor.fetchall():
        stats = dict(zip(STORED_KEYS, values, strict=True))
        stats["showdownWinnings"] = total_profit if saw_showdown else 0
        stats["nonShowdownWinnings"] = 0 if saw_showdown else total_profit
        rows[hid][pid] = stats
    return rows


def _store_session_ids(db: Any, hands: Sequence[Sequence[Any]]) -> None:
    """Point each hand and tournament of the batch at its session, as the import's insert does."""
    updates = []
    for hand in hands:
        hid, tourney_id = hand[0], hand[2]
        session = db.s.get(hid)
        if session is None:
            continue
        updates.append((session["id"], hid))
        if tourney_id:
            db.tbulk[tourney_id] = session["id"]
    if updates:
        query = SESSION_REBUILD_HAND_SESSION.replace("%s", db.sql.query["placeholder"])
        db.get_cursor().executemany(query, updates)
    db.updateTourneysSessions()
