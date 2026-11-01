"""The HUD's database threads: batched reads and connection recovery."""

import contextlib
import threading
from collections.abc import Callable
from queue import Empty, Queue
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from fpdb_3_legacy import Configuration, Database
from fpdb_3_legacy.db_reconnect import is_connection_lost
from fpdb_3_legacy.fast_fold_engine import (
    FastFoldEngine,
    FastFoldStatsRequest,
    FastFoldStatsResult,
)
from fpdb_3_legacy.hud_main_base import log
from fpdb_3_legacy.hud_read_service import (
    HudBatchReadRequest,
    HudReadService,
)

# How long the recovery worker waits between attempts to re-open a database
# connection that has dropped. Database.recover_connection has its own cooldown;
# this only decides how often we ask.
DB_RECOVERY_INTERVAL_S = 5.0



class DbRecoveryWorker(QThread):
    """Re-opens a dropped database connection away from the UI thread.

    Reconnecting costs a full connect timeout when the database is unreachable,
    which is exactly the stall the HUD must not take on the thread that repaints
    it. This thread owns the connection for the duration of the outage: it is
    started only once HudMain has stopped querying (the breaker is open) and it
    stops before HudMain resumes, so the connection still has a single user at
    any moment despite being touched from two threads.
    """

    recovered = Signal()

    def __init__(self, db_connection, parent: QObject | None = None) -> None:
        """Initialize the recovery worker."""
        super().__init__(parent)
        self.db_connection = db_connection
        # An Event rather than a sleep plus a flag, so closing the HUD during an
        # outage does not wait out the retry interval before shutting down.
        self._stopping = threading.Event()

    def run(self) -> None:
        """Retry the connection until it comes back or shutdown is requested."""
        log.info("Database recovery worker started")
        while not self._stopping.wait(DB_RECOVERY_INTERVAL_S):
            try:
                if self.db_connection.recover_connection():
                    log.info("Database connection recovered; resuming HUD updates")
                    self.recovered.emit()
                    return
            except Exception:
                log.exception("Database recovery attempt failed unexpectedly")

    def stop(self) -> None:
        """Stop the worker thread."""
        self._stopping.set()
        # Bounded: an attempt already inside connect() has to run out its own
        # connect timeout, but shutdown must not hang on it either.
        if not self.wait(15000):
            log.warning("Database recovery worker did not stop in time")



class HudReadWorker(QThread):
    """Own the HUD database connection and execute read batches off the UI thread."""

    ready = Signal(int)
    snapshot_ready = Signal(object)
    unavailable = Signal(str)
    batch_failed = Signal(object, str)
    fast_fold_stats_ready = Signal(object)

    def __init__(
        self,
        config: Configuration.Config,
        parent: QObject | None = None,
        db_factory: Callable[..., Any] = Database.Database,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.db_factory = db_factory
        # Batch reads and Fast-Fold reads share the one queue, and one thread.
        self._requests: Queue[HudBatchReadRequest | FastFoldStatsRequest | None] = Queue()
        # Newest queued Fast-Fold request id per table, so the worker can drop
        # the ones already superseded instead of reading for them. See submit().
        self._latest_fast_fold: dict[str, int] = {}
        self._latest_lock = threading.Lock()
        self._stopping = threading.Event()

    def submit(self, request: HudBatchReadRequest | FastFoldStatsRequest) -> None:
        """Queue one immutable request from the Qt thread.

        A Fast-Fold request also records itself as its table's newest. The ring
        grows a player at a time, so several reads for one table can be waiting
        at once, and every one of them but the last describes a table that has
        already changed. They used to be executed in full and discarded on
        arrival by request id -- the database did the work, the GUI threw the
        answer away. Now the worker drops them before reading.
        """
        if isinstance(request, FastFoldStatsRequest):
            with self._latest_lock:
                self._latest_fast_fold[request.temp_key] = request.request_id
        self._requests.put(request)

    def _is_superseded(self, request: FastFoldStatsRequest) -> bool:
        """Whether a newer read for the same table is already queued behind this one."""
        with self._latest_lock:
            latest = self._latest_fast_fold.get(request.temp_key)
        return latest is not None and latest != request.request_id

    def forget_fast_fold_table(self, temp_key: str) -> None:
        """Drop what is remembered about a table nobody is watching any more."""
        with self._latest_lock:
            self._latest_fast_fold.pop(temp_key, None)

    @staticmethod
    def _configure_session(database: Database.Database) -> None:
        """Bound only the worker's PostgreSQL statements, never the importer."""
        if database.backend != Database.Database.PGSQL:
            return
        with contextlib.suppress(Exception):
            database.connection.rollback()
        cursor = database.connection.cursor()
        try:
            cursor.execute("SET statement_timeout = 10000")
            cursor.execute("SET lock_timeout = 2000")
            cursor.execute("SET idle_in_transaction_session_timeout = 30000")
            database.connection.commit()
        finally:
            cursor.close()

    @staticmethod
    def _close_database(database: Database.Database | None) -> None:
        if database is None:
            return
        with contextlib.suppress(Exception):
            database.close_connection()

    @staticmethod
    def _read_fast_fold_stats(
        database: Database.Database,
        request: FastFoldStatsRequest,
    ) -> FastFoldStatsResult:
        """Read stats for the players a Fast-Fold table currently seats.

        Ends the read transaction the way HudReadService.read_batch does. On
        PostgreSQL a SELECT opens one, and leaving it open parks the connection
        "idle in transaction" holding its snapshot -- which stalls the importer
        writing alongside it, and eventually trips the worker's own
        idle_in_transaction_session_timeout.
        """
        try:
            gametype_id = None
            if request.hand_id is not None:
                info = database.get_gameinfo_from_hid(request.hand_id)
                gametype_id = info["gametypeId"] if info else None
            if gametype_id is None and request.site_name and request.pool_name:
                # A table the client log named before any of its hands was
                # imported. Without this the statistics query below is skipped
                # and the table's first update draws every block empty. Only
                # this pool's own hands are consulted, and only when the pool
                # is known: borrowing another table's stakes would be worse
                # than showing nothing.
                with contextlib.suppress(Exception):
                    gametype_id = database.get_last_gametype_id_for_table(
                        request.site_name,
                        request.pool_name,
                    )

            stat_dict = FastFoldEngine(db_connection=database).get_player_stats_for_seat_map(
                request.seat_map,
                db_conn=database,
                gametype_id=gametype_id,
                num_seats=request.num_seats,
            )
        finally:
            with contextlib.suppress(Exception):
                database.connection.rollback()

        return FastFoldStatsResult(
            temp_key=request.temp_key,
            seat_map=dict(request.seat_map),
            stat_dict=stat_dict,
            request_id=request.request_id,
        )

    def run(self) -> None:
        """Connect, process one request at a time, and reconnect in this thread."""
        database: Database.Database | None = None
        service: HudReadService | None = None
        pending: HudBatchReadRequest | FastFoldStatsRequest | None = None
        unavailable_announced = False
        while not self._stopping.is_set():
            if database is None:
                try:
                    database = self.db_factory(self.config)
                    self._configure_session(database)
                    service = HudReadService(self.config, database)
                except Exception as exc:
                    self._close_database(database)
                    database = None
                    service = None
                    if not unavailable_announced:
                        self.unavailable.emit(str(exc))
                        unavailable_announced = True
                    self._stopping.wait(DB_RECOVERY_INTERVAL_S)
                    continue
                unavailable_announced = False
                self.ready.emit(database.backend)

            if pending is None:
                try:
                    pending = self._requests.get(timeout=0.2)
                except Empty:
                    continue
                if pending is None:
                    break

            assert service is not None
            if isinstance(pending, FastFoldStatsRequest) and self._is_superseded(pending):
                # The table has moved on while this waited its turn. Reading for
                # it would spend a round trip on an answer the GUI discards.
                log.debug(
                    "Fast-Fold stats request %s for %s superseded before it ran",
                    pending.request_id,
                    pending.temp_key,
                )
                pending = None
                continue
            try:
                if isinstance(pending, FastFoldStatsRequest):
                    result = self._read_fast_fold_stats(database, pending)
                else:
                    snapshot = service.read_batch(pending, progress_callback=self.snapshot_ready.emit)
            except Exception as exc:
                if database is not None and is_connection_lost(database.backend, exc):
                    if not unavailable_announced:
                        self.unavailable.emit(str(exc))
                        unavailable_announced = True
                    self._close_database(database)
                    database = None
                    service = None
                    continue
                if isinstance(pending, FastFoldStatsRequest):
                    # Seats are refreshed on the next log line anyway, so a failed
                    # read is not worth the batch-retry machinery.
                    log.warning("Fast-Fold stats read failed for table %s: %s", pending.temp_key, exc)
                else:
                    self.batch_failed.emit(pending, str(exc))
            else:
                if isinstance(pending, FastFoldStatsRequest):
                    self.fast_fold_stats_ready.emit(result)
                else:
                    self.snapshot_ready.emit(snapshot)
            pending = None

        self._close_database(database)

    def stop(self) -> None:
        """Wake the queue and wait for the bounded statement timeout."""
        self._stopping.set()
        self._requests.put(None)
        if not self.wait(15000):
            log.warning("HUD read worker did not stop in time")

