"""Local-first sync: push locally imported hands to the server asynchronously (#680).

POC for the architecture explored in docs/680-hud-live-latency.md: when the
measured LAN RTT is above ~2-3 ms, the HUD reads a local embedded SQLite (0
RTT per statement) and a background worker pushes each imported hand to the
server database, which stays the source of truth for reports and other
machines.

Design notes:

* The server assigns hand ids (its own auto-increment); the local id is kept
  in ``fpdb_sync_outbox`` together with the server id, so notifications can be
  mapped. Dedup on the server is by the unique ``(siteHandNo, gametypeId)``
  index, so re-pushing is idempotent.
* Only the tables the HUD and the reports need are pushed here
  (Hands, HandsPlayers, HandsActions); the full list for production is in the
  design doc.
* The push runs in a transaction per batch, in a daemon thread, and never
  blocks the importer: failures are retried on the next poll.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from fpdb_3_legacy import latency_profile
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("local_first_sync")

OUTBOX_DDL = """
CREATE TABLE IF NOT EXISTS fpdb_sync_outbox (
    local_hand_id INTEGER PRIMARY KEY,
    server_hand_id INTEGER,
    pushed INTEGER NOT NULL DEFAULT 0,
    pushed_at TEXT
)
"""

# Tables pushed per hand, in FK-safe order. (table, local select cols)
PUSH_TABLES = ("Hands", "HandsPlayers", "HandsActions")


class LocalFirstSync:
    """Asynchronous push of local hands to the server database."""

    # pylint: disable=too-many-instance-attributes

    def __init__(
        self,
        local_db: Any,
        server_db_factory: Callable[[], Any],
        batch_size: int = 50,
        poll_s: float = 2.0,
        local_db_path: str | None = None,
    ) -> None:
        self.local_db = local_db
        self.server_db_factory = server_db_factory
        self.batch_size = batch_size
        self.poll_s = poll_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._bool_columns: dict[str, set[str]] = {}
        self._own_conn = None
        if local_db_path:
            import sqlite3

            self._own_conn = sqlite3.connect(local_db_path, check_same_thread=False)
            self._own_conn.execute("PRAGMA busy_timeout=60000")
        self._id_maps: dict[str, dict[Any, int]] = {}
        self._ensure_outbox()

    def _local_conn(self):
        """The worker's own SQLite connection when a path is known, so its
        commits never interleave with an in-flight import transaction (#680)."""
        return self._own_conn if self._own_conn is not None else self.local_db.connection

    def _ensure_outbox(self) -> None:
        c = self._local_conn().cursor()
        c.execute(OUTBOX_DDL)  # nosemgrep
        self._local_conn().commit()
        c.close()

    def mark(self, local_hand_ids: list) -> None:
        """Register locally imported hands for pushing (call after local commit)."""
        if not local_hand_ids:
            return
        c = self._local_conn().cursor()
        c.executemany(
            "INSERT OR IGNORE INTO fpdb_sync_outbox (local_hand_id) VALUES (?)"
            if self.local_db.backend == 4
            else "INSERT IGNORE INTO fpdb_sync_outbox (local_hand_id) VALUES (%s)",
            [(int(h),) for h in local_hand_ids],
        )
        self._local_conn().commit()
        c.close()

    def pending(self) -> list[int]:
        c = self._local_conn().cursor()
        c.execute(  # nosemgrep
            "SELECT local_hand_id FROM fpdb_sync_outbox WHERE pushed = 0 "
            f"ORDER BY local_hand_id LIMIT {self.batch_size}"  # nosec B608  # nosemgrep
        )
        rows = [r[0] for r in c.fetchall()]
        c.close()
        return rows

    def push_once(self) -> int:
        """Push one batch of pending hands; returns how many were pushed."""
        local_ids = self.pending()
        latency_profile.gauge("sync_outbox_pending", len(local_ids))
        if not local_ids:
            return 0
        pushed = 0
        done: list[tuple[int, int]] = []
        try:
            server = self.server_db_factory()
            sph = server.sql.query["placeholder"]
            with latency_profile.scope("sync_push_batch"):
                with server.transaction():
                    self._push_referentials(server, sph)
                    for local_id in local_ids:
                        server_id = self._push_hand(server, local_id, sph)
                        if server_id is not None:
                            # Marked locally only after the server commit: if this
                            # batch fails, nothing is marked and all of it is
                            # retried (#680 P0).
                            done.append((local_id, server_id))
            for local_id, server_id in done:
                self._mark_pushed(local_id, server_id)
            pushed = len(done)
        except Exception:
            latency_profile.count("sync_push_errors")
            raise
        finally:
            server = locals().get("server")
            if server is not None:
                try:
                    server.close_connection()
                except Exception:
                    pass  # nosec B110  # nosemgrep
        latency_profile.gauge("sync_outbox_pending", len(self.pending()))
        return pushed

    # Referential tables pushed before any hand, deduped by their natural keys,
    # so the server's foreign keys hold. (table, dedup columns)
    # A game type is identified by every column: hands at other stakes, in
    # another currency or at another table size must not share a server row.
    REFERENTIALS = (
        ("Sites", ("name",)),
        ("Players", ("name", "siteId")),
        ("Files", ("file",)),
        (
            "Gametypes",
            (
                "siteId",
                "currency",
                "type",
                "base",
                "category",
                "limitType",
                "hiLo",
                "mix",
                "smallBlind",
                "bigBlind",
                "smallBet",
                "bigBet",
                "maxSeats",
                "ante",
                "buyinType",
                "fast",
                "newToGame",
                "homeGame",
                "split",
            ),
        ),
    )

    def _server_bool_columns(self, server: Any, table: str) -> set[str]:
        """Boolean columns of ``table`` on the server, so SQLite's 0/1 ints are
        cast to real booleans (PostgreSQL rejects smallint into boolean)."""
        if table in self._bool_columns:
            return self._bool_columns[table]
        from fpdb_3_legacy.Database import Database

        cols: set[str] = set()
        if server.backend == Database.PGSQL:
            c = server.connection.cursor()
            c.execute(  # nosemgrep
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND data_type = 'boolean'",
                (table.lower(),),
            )
            cols = {r[0].lower() for r in c.fetchall()}
            c.close()
        self._bool_columns[table] = cols
        return cols

    @staticmethod
    def _server_value(column: str, value: Any, bools: set[str]) -> Any:
        """``value`` as the server's ``column`` expects it (see _server_bool_columns)."""
        return bool(value) if column.lower() in bools and value is not None else value

    def _push_referentials(self, server: Any, sph: str) -> None:
        lc = self._local_conn().cursor()
        c = server.connection.cursor()
        for table, keys in self.REFERENTIALS:
            lc.execute(f"SELECT * FROM {table}")  # nosec B608  # nosemgrep
            rows = lc.fetchall()
            if not rows:
                continue
            cols = [d[0] for d in lc.description]
            bools = self._server_bool_columns(server, table)
            sites_map = self._id_maps.get("Sites", {})
            for row in rows:
                record = dict(zip(cols, row))
                if "siteId" in record:
                    record["siteId"] = sites_map.get(record["siteId"], record["siteId"])
                # NULL never matches "=", and PostgreSQL rejects an int against a
                # boolean column, so the lookup is built from the row's values.
                where = " AND ".join(f"{k} IS NULL" if record[k] is None else f"{k} = {sph}" for k in keys)
                params = [self._server_value(k, record[k], bools) for k in keys if record[k] is not None]
                c.execute(f"SELECT id FROM {table} WHERE {where}", params)  # nosec B608  # nosemgrep
                existing = c.fetchone()
                if existing:
                    # local id -> server id, so child FKs can be remapped (#680 P0)
                    self._id_maps.setdefault(table, {})[record.get("id")] = existing[0]
                    continue
                insert_cols = [k for k in cols if k != "id"]
                values = [self._server_value(k, record[k], bools) for k in insert_cols]
                ph_values = ", ".join([sph] * len(insert_cols))
                q = f"INSERT INTO {table} ({', '.join(insert_cols)}) VALUES ({ph_values})"  # nosec B608  # nosemgrep
                c.execute(q, values)  # nosemgrep
                self._id_maps.setdefault(table, {})[record.get("id")] = self._last_insert_id(server, c)
        lc.close()

    def _push_hand(self, server: Any, local_id: int, sph: str) -> int | None:
        """Insert one hand server-side, dedup by (siteHandNo, gametypeId).

        Returns the server hand id, or None if the hand already existed.
        """
        lc = self._local_conn().cursor()
        lc.execute(f"SELECT * FROM Hands WHERE id = {self._ph()} ", (local_id,))  # nosec B608  # nosemgrep
        row = lc.fetchone()
        if row is None:
            lc.close()
            return None
        cols = [d[0] for d in lc.description]
        hand = dict(zip(cols, row))

        lc.close()

        self._remap_hand_fks(hand)

        # dedup check
        c = server.connection.cursor()
        c.execute(  # nosemgrep
            f"SELECT id FROM Hands WHERE siteHandNo = {sph} AND gametypeId = {sph}",  # nosec B608  # nosemgrep
            (hand["siteHandNo"], hand["gametypeId"]),
        )
        existing = c.fetchone()
        if existing:
            return existing[0]

        # insert the hand without its local id; the server assigns one
        insert_cols = [k for k in cols if k != "id"]
        bools = self._server_bool_columns(server, "Hands")
        q = f"INSERT INTO Hands ({', '.join(insert_cols)}) VALUES ({', '.join([sph] * len(insert_cols))})"  # nosec B608  # nosemgrep
        values = [bool(hand[k]) if k.lower() in bools and hand[k] is not None else hand[k] for k in insert_cols]
        c.execute(q, values)  # nosemgrep
        server_id = self._last_insert_id(server, c)

        # child rows, remapped to the server hand id and server referential ids
        for table in ("HandsPlayers", "HandsActions"):
            self._push_children(server, table, local_id, server_id, sph)
        return server_id

    def _remap_hand_fks(self, hand: dict) -> None:
        """Rewrite the hand's referential FKs from local ids to server ids
        using the maps built by _push_referentials (#680 P0)."""
        for fk_col, ref_table in (("gametypeId", "Gametypes"), ("fileId", "Files"), ("siteId", "Sites")):
            if hand.get(fk_col) is not None:
                hand[fk_col] = self._id_maps.get(ref_table, {}).get(hand[fk_col], hand[fk_col])
        # Sessions are a cache, recomputed server-side and never pushed (see the
        # design doc): the local id means nothing on the server, where it either
        # breaks the foreign key or points at someone else's session.
        hand["sessionId"] = None

    def _push_children(self, server: Any, table: str, local_id: int, server_id: int, sph: str) -> None:
        lc = self._local_conn().cursor()
        lc.execute(f"SELECT * FROM {table} WHERE handId = {self._ph()}", (local_id,))  # nosec B608  # nosemgrep
        child_rows = lc.fetchall()
        child_cols = [d[0] for d in lc.description]
        lc.close()
        if not child_rows:
            return
        c = server.connection.cursor()
        bools = self._server_bool_columns(server, table)
        ins_cols = [k for k in child_cols if k != "id"]  # server assigns its own PKs
        players_map = self._id_maps.get("Players", {})
        for child in child_rows:
            values = []
            for k, v in zip(child_cols, child):
                if k == "id":
                    continue
                if k == "handId":
                    values.append(server_id)
                elif k == "playerId" and v is not None:
                    values.append(players_map.get(v, v))
                elif k.lower() in bools and v is not None:
                    values.append(bool(v))
                else:
                    values.append(v)

            cph = ", ".join([sph] * len(ins_cols))
            cq = f"INSERT INTO {table} ({', '.join(ins_cols)}) VALUES ({cph})"  # nosec B608  # nosemgrep
            c.execute(cq, values)  # nosemgrep
        c.close()

    def _ph(self) -> str:
        return self.local_db.sql.query["placeholder"]

    def _last_insert_id(self, server: Any, cursor: Any) -> int:
        getter = getattr(server, "get_last_insert_id", None)
        if getter is not None:
            return int(getter(cursor))
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def _mark_pushed(self, local_id: int, server_id: int) -> None:
        ph = self._ph()
        c = self._local_conn().cursor()
        c.execute(  # nosec B608  # nosemgrep
            "UPDATE fpdb_sync_outbox SET pushed = 1, server_hand_id = "  # nosec B608
            + ph
            + ", pushed_at = "
            + ph
            + f" WHERE local_hand_id = {ph}",  # nosec B608  # nosemgrep
            (server_id, time.strftime("%Y-%m-%d %H:%M:%S"), local_id),
        )
        self._local_conn().commit()
        c.close()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="local-first-sync")
        self._thread.start()

    def stop(self) -> None:
        """Stop the push thread and close the dedicated local connection."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        if self._own_conn is not None:
            try:
                self._own_conn.close()
            except Exception:
                pass  # nosec B110
            self._own_conn = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.push_once()
            except Exception:
                log.exception("local-first push failed; will retry")
            self._stop.wait(self.poll_s)


class ServerConfigView:
    """Adapts a Config so Database opens the *server* database while the main
    config is switched to local-first: every method delegates, only
    get_db_parameters returns the server params (#680)."""

    def __init__(self, config: Any) -> None:
        self._config = config

    def get_db_parameters(self) -> dict:
        return self._config.get_server_db_parameters()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._config, name)
