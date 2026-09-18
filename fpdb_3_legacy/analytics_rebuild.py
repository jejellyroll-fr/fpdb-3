"""In-place rebuild and backfill of the analytics-derived rows (issue #305).

The importer derives events, board features and situations while it parses;
a database imported before those layers existed has hands but none of the
derived rows. Re-importing every file is the sledgehammer -- it needs the
original files, it moves hand ids, and it rebuilds the HUD cache from
scratch. This module re-derives the rows **in place**, from the rows the
database already stores:

* the action stream, the players' seats, stacks and positions, the board
  cards and the gametype are read back out of ``HandsActions`` /
  ``HandsPlayers`` / ``Hands`` / ``Gametypes`` and assembled into a
  hand-like adapter (``backfill_autonotes.DatabaseAutoNoteHand`` does the
  same for AutoNotes); the extractors then run over it unchanged -- one set
  of rules, executed against either a freshly parsed hand or its stored
  rows;
* every write is one transaction per hand, so a cancelled rebuild leaves
  each finished hand complete and the rest untouched -- never a half
  written hand, and the run can resume over the same scope without
  corrupting anything;
* progress is reported per hand and cancellation is checked before each
  hand; scopes (site, date range, hand ids, row limit) shrink the work
  instead of filtering the truth afterwards.

What each subsystem's rebuild actually does:

* ``board_features`` re-classifies from the stored cards and overwrites the
  ``BoardFeatures`` rows and ``Hands.texture``;
* ``action_events`` re-derives over the stored action stream and updates
  the event columns in place; ``situations`` re-derives over the refreshed
  events and overwrites the hand's ``HandsSituations`` rows;
* ``sizing_buckets`` needs no pass of its own: buckets are pure functions
  of the persisted sizing columns, so they come back current the moment
  the events are -- the subsystem is marked current with the events.

There is deliberately no re-parse from raw hand-history text: the importer
never wrote one (``RawHands`` is empty in every database this code has ever
produced), so the stored rows are the only source of truth available --
which is exactly why the extractors accept stored rows as input.

Downgrade of the derived rows is deliberately absent: re-deriving from
older rules would mean keeping every old extractor alive forever. The
version record (``analytics_lifecycle``) says which rules wrote the rows;
the rows themselves are simply stale until rebuilt.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from . import analytics_lifecycle as lifecycle
from .action_events import ACTION_EVENT_COLUMNS, attach_action_events, chips_to_cents
from .backfill_autonotes import _decode_card, load_hand_from_database
from .board_features import BOARD_FEATURE_COLUMNS, derive_board_rows, flop_texture_mask
from .player_situations import enumerate_situations

log = logging.getLogger(__name__)

# Progress callback: (hands_done, hands_total, current_hand_id). Optional for
# every adapter; callers that pass one get it once per hand.
ProgressCallback = Callable[[int, int, int], None]

# Subsystems whose stored rows are refreshed as a side effect of another's
# pass. sizing_buckets is a pure function of the event columns, so its rows
# come back current with the events that carry the sizes.
GROUPED_WITH: dict[str, str] = {"sizing_buckets": "action_events"}


class RebuildCancelled(Exception):
    """Raised by the coordinator when the caller asked to stop.

    Every hand already finished is committed -- the per-hand transaction
    guarantees it -- and the run can be resumed over the same scope.
    """


@dataclass
class RebuildScope:
    """Which hands a rebuild touches; the default is everything."""

    site: str | None = None
    date_from: Any = None  # inclusive lower bound on Hands.startTime
    date_to: Any = None  # inclusive upper bound
    hand_ids: list[int] | None = None
    limit: int | None = None

    @property
    def is_whole_database(self) -> bool:
        """True when the scope selects every hand, which is what "current" means.

        The version stamped by a run says "every derived row in this database
        is at this version". Only a run that looked at every hand can say it.
        """
        return not any((self.site, self.date_from, self.date_to, self.hand_ids is not None, self.limit))


@dataclass
class RebuildResult:
    """What one rebuild run did, for the CLI and the GUI."""

    subsystems: tuple[str, ...]
    scanned: int = 0
    rebuilt: int = 0
    skipped: int = 0
    failed: int = 0
    cancelled: bool = False
    failures: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "subsystems": list(self.subsystems),
            "scanned": self.scanned,
            "rebuilt": self.rebuilt,
            "skipped": self.skipped,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "failures": list(self.failures),
        }


def canonical_subsystems(requested: Iterable[str]) -> tuple[str, ...]:
    """Expand sizing_buckets into the pass that refreshes it; validate names.

    ``hand_strength`` fails loudly: it is declared in the lifecycle registry
    (so staleness is expressible for it) but has no extractor until #302,
    and silently doing nothing would stamp it current.
    """
    out: list[str] = []
    for name in requested:
        if name not in lifecycle.SUBSYSTEMS:
            raise ValueError(f"Unknown analytics subsystem: {name!r}")
        if name == "hand_strength":
            raise ValueError("hand_strength has no extractor yet (#302); nothing to rebuild")
        name = GROUPED_WITH.get(name, name)
        if name not in out:
            out.append(name)
    return tuple(out)


def _scope_sql(db: Any, scope: RebuildScope) -> tuple[str, list[Any]]:
    """The scope as a WHERE clause, in the backend's own placeholder.

    SQLite marks a parameter with ``?`` and the two server backends with
    ``%s``; writing one of them here made every scoped rebuild -- a site, a
    date range, a list of hand ids -- fail on MySQL and PostgreSQL.
    """
    ph = db.sql.query["placeholder"]
    where = ["1=1"]
    params: list[Any] = []
    if scope.site is not None:
        where.append(f"G.siteId IN (SELECT id FROM Sites WHERE name = {ph})")  # nosec B608  # nosemgrep
        params.append(scope.site)
    if scope.date_from is not None:
        where.append(f"H.startTime >= {ph}")  # nosec B608  # nosemgrep
        params.append(scope.date_from)
    if scope.date_to is not None:
        where.append(f"H.startTime <= {ph}")  # nosec B608  # nosemgrep
        params.append(scope.date_to)
    if scope.hand_ids is not None:
        if not scope.hand_ids:
            where.append("1=0")
        else:
            where.append(f"H.id IN ({', '.join(ph for _ in scope.hand_ids)})")  # nosec B608  # nosemgrep
            params.extend(scope.hand_ids)
    return " AND ".join(where), params


def _iter_scope_hand_ids(db: Any, scope: RebuildScope) -> Iterator[int]:
    """The hand ids the scope selects, ascending -- the resume-friendly order."""
    c = db.get_cursor()
    where, params = _scope_sql(db, scope)
    sql = f"SELECT H.id FROM Hands H JOIN Gametypes G ON H.gametypeId = G.id WHERE {where} ORDER BY H.id"  # nosec B608  # nosemgrep
    if scope.limit is not None:
        sql += f" LIMIT {int(scope.limit)}"  # nosec B608  # nosemgrep
    c.execute(sql, tuple(params))
    for row in c.fetchall():
        yield int(row[0])


def _count_scope_hands(db: Any, scope: RebuildScope) -> int:
    c = db.get_cursor()
    where, params = _scope_sql(db, scope)
    c.execute(
        f"SELECT COUNT(*) FROM Hands H JOIN Gametypes G ON H.gametypeId = G.id WHERE {where}",  # nosec B608  # nosemgrep
        tuple(params),
    )
    return int(c.fetchone()[0])


def _hand_has_actions(db: Any, hand_id: int) -> bool:
    """False for a hand whose importer predates even the raw action rows."""
    c = db.get_cursor()
    ph = db.sql.query["placeholder"]
    c.execute(f"SELECT 1 FROM HandsActions WHERE handId = {ph} LIMIT 1", (hand_id,))  # nosec B608  # nosemgrep
    return c.fetchone() is not None


def _restore_extra_boards(db: Any, hand: Any) -> None:
    """Put the other runs of a run-it-twice hand back on the hand.

    ``Hands`` carries one board and the database adapter reads only that one,
    so a rebuild saw a single run, deleted the features of every other and
    wrote none back. The runs are in ``Boards``, one complete five-card row per
    run, which is the shape ``_assembleRunItTwiceBoards`` wrote them in.
    """
    c = db.get_cursor()
    ph = db.sql.query["placeholder"]
    c.execute(
        "SELECT boardId, boardcard1, boardcard2, boardcard3, boardcard4, boardcard5"
        f" FROM Boards WHERE handId = {ph} ORDER BY boardId",  # nosec B608  # nosemgrep
        (int(hand.dbid_hands),),
    )
    rows = c.fetchall()
    if len(rows) < 2:  # one board is the hand's own, and it is already there
        return
    for index, row in enumerate(rows, start=1):
        run = int(row[0] or index)
        cards = [_decode_card(value) for value in row[1:6]]
        hand.board[f"FLOP{run}"] = [card for card in cards[:3] if card]
        hand.board[f"TURN{run}"] = [cards[3]] if cards[3] else []
        hand.board[f"RIVER{run}"] = [cards[4]] if cards[4] else []
    hand.runItTimes = len(rows)


def _rebuild_board_features(db: Any, hand: Any) -> None:
    """Re-classify the board from the stored cards and overwrite the rows."""
    rows = derive_board_rows(hand)
    hand_id = int(hand.dbid_hands)
    c = db.get_cursor()
    ph = db.sql.query["placeholder"]
    c.execute(f"DELETE FROM BoardFeatures WHERE handId = {ph}", (hand_id,))  # nosec B608  # nosemgrep
    for row in rows:
        columns = ", ".join(("handId", *BOARD_FEATURE_COLUMNS))
        placeholders = ", ".join(ph for _ in range(len(BOARD_FEATURE_COLUMNS) + 1))
        c.execute(
            f"INSERT INTO BoardFeatures ({columns}) VALUES ({placeholders})",  # nosec B608  # nosemgrep
            (hand_id, *(row.get(column) for column in BOARD_FEATURE_COLUMNS)),
        )
    c.execute(
        f"UPDATE Hands SET texture = {ph} WHERE id = {ph}",  # nosec B608  # nosemgrep
        (flop_texture_mask(rows), hand_id),
    )


def _rebuild_action_rows(
    db: Any,
    hand: Any,
    handsplayers: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    """Re-derive the event context and update the stored HandsActions rows.

    The stored rows are read back in action order and re-run through
    ``attach_action_events`` -- the same derivation the import path uses,
    so the update can only ever agree with a fresh import of the same hand.
    """
    handsactions = _load_action_rows(db, hand, handsplayers)
    c = db.get_cursor()
    ph = db.sql.query["placeholder"]
    assignments = ", ".join(f"{column} = {ph}" for column in ACTION_EVENT_COLUMNS)
    for number, event in handsactions.items():
        values = [event.get(column) for column in ACTION_EVENT_COLUMNS]
        c.execute(
            f"UPDATE HandsActions SET {assignments} WHERE handId = {ph} AND actionNo = {ph}",  # nosec B608  # nosemgrep
            (*values, hand.dbid_hands, number),
        )
    return handsactions


def _load_action_rows(
    db: Any,
    hand: Any,
    handsplayers: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    """One hand's action rows, in order, with their event context derived.

    Reading only: the situations of a hand are a function of its events, so a
    ``--subsystems situations`` run needs them without touching the rows the
    action-event pass owns. Deriving them here rather than reading the stored
    event columns keeps a situations-only rebuild identical to a full one.
    """
    handsactions: dict[int, dict[str, Any]] = {}
    c = db.get_cursor()
    ph = db.sql.query["placeholder"]
    c.execute(
        "SELECT HA.street, HA.actionNo, HA.streetActionNo, HA.amount, HA.raiseTo,"
        " HA.amountCalled, HA.numDiscarded, HA.cardsDiscarded, HA.allIn, P.name AS name,"
        " A.name AS actionName"
        " FROM HandsActions HA JOIN Players P ON HA.playerId = P.id"
        f" LEFT JOIN Actions A ON HA.actionId = A.id WHERE HA.handId = {ph}"  # nosec B608  # nosemgrep
        " ORDER BY HA.actionNo",
        (hand.dbid_hands,),
    )
    names = [d[0] for d in c.description]
    for raw in c.fetchall():
        row = dict(zip(names, raw, strict=True))
        number = int(row["actionNo"])
        stored = handsactions.get(number)
        if stored is None:
            stored = handsactions[number] = {
                "player": row["name"],
                "street": row["street"],
                "actionNo": number,
                "streetActionNo": row["streetActionNo"],
                "amount": row["amount"] or 0,
                "raiseTo": row["raiseTo"] or 0,
                "amountCalled": row["amountCalled"] or 0,
                "numDiscarded": row["numDiscarded"] or 0,
                "cardsDiscarded": row["cardsDiscarded"],
                "allIn": bool(row["allIn"]),
            }
        stored.setdefault("actionType", row.get("actionName"))
    attach_action_events(handsactions, hand, handsplayers)
    return handsactions


def _rebuild_situations(
    db: Any,
    hand: Any,
    handsplayers: dict[str, Any],
    handsactions: dict[int, Any],
) -> None:
    """Re-derive the situations and overwrite the hand's HandsSituations rows."""
    situations = enumerate_situations(hand, handsplayers, handsactions)
    hand_id = int(hand.dbid_hands)
    c = db.get_cursor()
    ph = db.sql.query["placeholder"]
    c.execute(f"DELETE FROM HandsSituations WHERE handId = {ph}", (hand_id,))  # nosec B608  # nosemgrep
    # bulk_rows emits [handId, playerId, *HANDS_SITUATION_COLUMNS] -- one row
    # per situation in store order, identical to the importer's write.
    rows = bulk_rows(hand_id, hand.playerIds, list(situations), lifecycle.EXTRACTOR_VERSIONS["situations"])
    if rows:
        columns = ", ".join(("handId", "playerId", *HANDS_SITUATION_COLUMNS, "situationVersion"))
        placeholders = ", ".join(ph for _ in range(len(rows[0])))
        c.executemany(
            f"INSERT INTO HandsSituations ({columns}) VALUES ({placeholders})",  # nosec B608  # nosemgrep
            rows,
        )


# Late import target: the column list behind the two id columns and the row
# writer, kept as module-level names so _rebuild_situations stays readable.
from .situation_store import HANDS_SITUATION_COLUMNS, bulk_rows  # noqa: E402


class AnalyticsRebuilder:
    """Rebuilds analytics rows in place, one hand per transaction."""

    def __init__(self, db: Any, config: Any) -> None:
        self.db = db
        self.config = config

    def run(
        self,
        subsystems: Iterable[str],
        scope: RebuildScope | None = None,
        progress: ProgressCallback | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> RebuildResult:
        """Re-derive the requested subsystems over the scope, hand by hand."""
        scope = scope or RebuildScope()
        wanted = canonical_subsystems(subsystems)
        result = RebuildResult(subsystems=tuple(subsystems))
        want_boards = "board_features" in wanted
        want_events = "action_events" in wanted
        want_situations = "situations" in wanted

        total = _count_scope_hands(self.db, scope)
        for done, hand_id in enumerate(_iter_scope_hand_ids(self.db, scope), start=1):
            if should_cancel is not None and should_cancel():
                result.cancelled = True
                log.info("Analytics rebuild cancelled after %d hands", result.rebuilt)
                break
            if progress is not None:
                progress(done, total, hand_id)
            result.scanned += 1
            try:
                with self.db.transaction():
                    hand = load_hand_from_database(self.db, hand_id)
                    # Only the passes that read actions need them. A hand
                    # imported with saveActions off still has its board in
                    # Hands, and skipping it for a board rebuild left the
                    # subsystem stamped current with those rows missing.
                    needs_actions = want_events or want_situations
                    if hand is None or (needs_actions and not _hand_has_actions(self.db, hand_id)):
                        result.skipped += 1
                        continue
                    self._rebuild_hand(hand, want_boards, want_events, want_situations)
                result.rebuilt += 1
            except Exception as exc:  # noqa: BLE001 - one bad hand must not stop the run
                result.failed += 1
                result.failures.append(f"hand {hand_id}: {exc}")
                log.exception("Analytics rebuild failed for hand %s", hand_id)

        if not result.cancelled and scope.is_whole_database:
            # Only a completed run over the whole database marks the versions
            # current. A cancelled run leaves the hands it never reached stale,
            # and so does a scoped one -- a site, a date range, a --limit: the
            # hands outside the scope still carry old or missing rows, and
            # stamping the subsystem current would hide exactly them.
            markable = list(wanted) + [name for name, target in GROUPED_WITH.items() if target in wanted]
            lifecycle.mark_current(self.db, *markable)
        return result

    @staticmethod
    def _money_in_cents(handsplayers: dict[str, Any]) -> dict[str, Any]:
        """The per-player context with its money back in the cents the derivators read.

        ``DatabaseAutoNoteHand`` hands money out in chips -- it divides the
        stored cents by 100, because the note rules it was written for speak in
        chips -- while the event walk and the situation model read the same
        columns as the cents ``assembleHandsPlayers`` writes. Left alone, a
        replayed stack is a hundredth of the real one, which zeroes the
        effective stack after the first bet and moves every rebuilt SPR and
        stack bucket away from the imported one.
        """
        money = ("startCash", "effStack", "totalProfit", "showdownWinnings")
        return {
            name: {
                **row,
                **{key: chips_to_cents(row[key]) for key in money if row.get(key) is not None},
            }
            for name, row in handsplayers.items()
        }

    def _rebuild_hand(self, hand: Any, want_boards: bool, want_events: bool, want_situations: bool) -> None:
        """One hand's worth of re-derivation, inside the caller's transaction."""
        if want_boards:
            # The DB adapter carries board cards but no street names; the
            # classifier reads communityStreets, so name the streets that
            # actually dealt cards.
            if not getattr(hand, "communityStreets", None):
                hand.communityStreets = [street for street in ("FLOP", "TURN", "RIVER") if hand.board.get(street)]
            _restore_extra_boards(self.db, hand)
            _rebuild_board_features(self.db, hand)
        handsplayers = self._money_in_cents(hand.handsplayers)
        handsactions: dict[int, Any] = {}
        if want_events:
            handsactions = _rebuild_action_rows(self.db, hand, handsplayers)
        if want_situations:
            # A situations-only run still needs the events they are derived
            # from; without them every situation of the hand was deleted and
            # none written back.
            if not want_events:
                handsactions = _load_action_rows(self.db, hand, handsplayers)
            _rebuild_situations(self.db, hand, handsplayers, handsactions)


def rebuild_subsystems(
    db: Any,
    config: Any,
    subsystems: Iterable[str],
    scope: RebuildScope | None = None,
    progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> RebuildResult:
    """Module-level entry point: rebuild analytics rows on an open database."""
    return AnalyticsRebuilder(db, config).run(
        subsystems,
        scope=scope,
        progress=progress,
        should_cancel=should_cancel,
    )
