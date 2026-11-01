"""Database module for FPDB.
from __future__ import annotations
Copyright 2008-2011, Ray E. Barker

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

Create and manage the database objects.
"""

import contextlib
import math

#    Standard Library modules
import os
import queue
import re
import sys
import threading
import traceback
import weakref
from decimal import Decimal
from time import sleep, time
from typing import Any

from cachetools import TTLCache

from fpdb_3_legacy import SQL, Card, Configuration, db_profile
from fpdb_3_legacy.database_aof import DatabaseAofMixin
from fpdb_3_legacy.database_auto_notes import DatabaseAutoNotesMixin
from fpdb_3_legacy.database_bulk_import import DatabaseBulkImportMixin

# CACHE_KEYS and HUDCACHE_EXTRA_KEYS moved to database_caches with the code that
# writes those columns; re-exported here because tests and callers still import
# them from Database. The redundant alias marks the re-export for the linters.
from fpdb_3_legacy.database_caches import CACHE_KEYS as CACHE_KEYS
from fpdb_3_legacy.database_caches import HUDCACHE_EXTRA_KEYS as HUDCACHE_EXTRA_KEYS
from fpdb_3_legacy.database_caches import DatabaseCachesMixin
from fpdb_3_legacy.database_connection import DatabaseConnectionMixin
from fpdb_3_legacy.database_hud_stats import DatabaseHudStatsMixin
from fpdb_3_legacy.database_lambda_dict import LambdaDict
from fpdb_3_legacy.database_players import DatabasePlayersMixin
from fpdb_3_legacy.database_queries import DatabaseQueriesMixin
from fpdb_3_legacy.database_rebuild import DatabaseRebuildMixin
from fpdb_3_legacy.database_schema import DB_VERSION, DatabaseSchemaMixin

# HANDS_PLAYERS_KEYS moved to database_schema with the DDL that checks those
# columns; re-exported because four test modules import it from Database.
from fpdb_3_legacy.database_schema import HANDS_PLAYERS_KEYS as HANDS_PLAYERS_KEYS
from fpdb_3_legacy.database_tournaments import DatabaseTournamentsMixin
from fpdb_3_legacy.db_reconnect import (
    PG_NETWORK_KWARGS,
)
from fpdb_3_legacy.Exceptions import (
    FpdbError,
)
from fpdb_3_legacy.loggingFpdb import get_logger

# #import L10n
# #_ = L10n.get_translation()

########################################################################

# Database maintenance is available through ``rebuild_indexes()``,
# ``analyzeDB()`` and ``vacuumDB()`` as well as the command-line utility below.

# postmaster -D /var/lib/pgsql/data


re_char = re.compile("[^a-zA-Z]")

# Gametype-per-hand cache. A hand's game is fixed when the hand is written, so
# the TTL is only there to bound how long a re-imported hand could be served
# from a stale entry; the size bounds a long multi-tabling session.
GAMEINFO_CACHE_SIZE = 2000
GAMEINFO_CACHE_TTL = 3600


if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("database")

# The connection helpers moved to database_connection with the code that uses
# them (#452); re-exported because callers and tests still reach them here.
from fpdb_3_legacy.database_connection import SQLITE_SYNCHRONOUS_PRAGMA as SQLITE_SYNCHRONOUS_PRAGMA
from fpdb_3_legacy.database_connection import VARIANCE as VARIANCE
from fpdb_3_legacy.database_connection import DatabaseTransaction as DatabaseTransaction
from fpdb_3_legacy.database_connection import _mysql_connection_kwargs as _mysql_connection_kwargs
from fpdb_3_legacy.database_connection import adapt_decimal as adapt_decimal
from fpdb_3_legacy.database_connection import convert_decimal as convert_decimal
from fpdb_3_legacy.database_connection import sqlitemath as sqlitemath
from fpdb_3_legacy.database_connection import use_numpy as use_numpy

#    Other library modules
# Note: SQLAlchemy pool.manage was removed in 2.0
# Each database driver (MySQLdb, psycopg, sqlite3) now handles its own connection pooling
# SQLAlchemy import kept for potential future use of core features
try:
    import sqlalchemy  # noqa: F401 -- availability probe

    use_sqlalchemy = True
except ImportError:
    log.info("SQLAlchemy not available (optional dependency)")
    use_sqlalchemy = False


class Database(
    DatabaseConnectionMixin,
    DatabaseQueriesMixin,
    DatabaseRebuildMixin,
    DatabaseAofMixin,
    DatabaseAutoNotesMixin,
    DatabaseBulkImportMixin,
    DatabaseCachesMixin,
    DatabaseHudStatsMixin,
    DatabasePlayersMixin,
    DatabaseSchemaMixin,
    DatabaseTournamentsMixin,
):
    MYSQL_INNODB = 2
    PGSQL = 3
    SQLITE = 4

    # The semaphore is global on purpose: it bounds how many worker
    # connections this *process* holds open at once, which is a limit about
    # the process rather than about any one database. Idle connections are
    # counted separately and evicted before opening a connection for another
    # database, so the active limit and the total open-connection limit agree.
    _worker_conn_semaphore = threading.Semaphore(4)
    _worker_pool_lock = threading.Lock()
    _worker_idle_connections = 0
    _worker_idle_limit = 4
    _worker_pools: weakref.WeakSet[Any] = weakref.WeakSet()
    # A worker may still be inside ``worker_connection`` after its database
    # tab has retired the idle pool.  Keep that identity briefly so its return
    # path closes the borrowed connection instead of enqueueing it into an
    # unreachable queue.
    _worker_retired_pools: weakref.WeakSet[Any] = weakref.WeakSet()

    hero_hudstart_def = "1999-12-31"  # default for length of Hero's stats in HUD
    villain_hudstart_def = "1999-12-31"  # default for length of Villain's stats in HUD

    # Data Structures for index and foreign key creation
    # drop_code is an int with possible values:  0 - don't drop for bulk import
    #                                            1 - drop during bulk import
    # MySQL Notes:
    #    "FOREIGN KEY (handId) REFERENCES Hands(id)" - requires index on Hands.id
    #                                                - creates index handId on <thistable>.handId
    # alter table t drop foreign key fk
    # alter table t add foreign key (fkcol) references tab(rcol)
    # alter table t add constraint c foreign key (fkcol) references tab(rcol)
    # (fkcol is used for foreigh key name)

    # mysql to list indexes: (CG - "LIST INDEXES" should work too)
    #   SELECT table_name, index_name, non_unique, column_name
    #   FROM INFORMATION_SCHEMA.STATISTICS
    #     WHERE table_name = 'tbl_name'
    #     AND table_schema = 'db_name'
    #   ORDER BY table_name, index_name, seq_in_index
    #
    # ALTER TABLE Tourneys ADD INDEX siteTourneyNo(siteTourneyNo)
    # ALTER TABLE tab DROP INDEX idx

    # mysql to list fks:
    #   SELECT constraint_name, table_name, column_name, referenced_table_name, referenced_column_name
    #   FROM information_schema.KEY_COLUMN_USAGE
    #   WHERE REFERENCED_TABLE_SCHEMA = (your schema name here)
    #   AND REFERENCED_TABLE_NAME is not null
    #   ORDER BY TABLE_NAME, COLUMN_NAME;

    # this may indicate missing object
    # _mysql_exceptions.OperationalError: (1025, "Error on rename of '.\\fpdb\\hands' to '.\\fpdb\\#sql2-7f0-1b' (errno: 152)")

    # PG notes:

    #  To add a foreign key constraint to a table:
    #  ALTER TABLE tab ADD CONSTRAINT c FOREIGN KEY (col) REFERENCES t2(col2) MATCH FULL;
    #  ALTER TABLE tab DROP CONSTRAINT zipchk
    #
    #  Note: index names must be unique across a schema
    #  CREATE INDEX idx ON tab(col)
    #  DROP INDEX idx
    #  SELECT * FROM PG_INDEXES

    # SQLite notes:

    # To add an index:
    # create index indexname on tablename (col);

    def __init__(self, c, sql=None, autoconnect=True) -> None:
        self.config = c
        # Connection/cursor implementations differ across SQLite, PostgreSQL,
        # MySQLdb and pymysql, so the common database facade treats them as a
        # backend-defined runtime interface.
        self.connection: Any = None
        self.cursor: Any = None
        self._worker_conn_pool: queue.Queue[Any] = queue.Queue()
        with Database._worker_pool_lock:
            Database._worker_pools.add(self._worker_conn_pool)
            Database._worker_retired_pools.discard(self._worker_conn_pool)
        self.__connected = False
        self.wrongDbVersion = False
        self.settings = {}
        self.settings["os"] = "linuxmac" if os.name != "nt" else "windows"
        db_params = c.get_db_parameters()
        self.import_options = c.get_import_parameters()
        self.backend = db_params["db-backend"]
        self.db_server = db_params["db-server"]
        self.database = db_params["db-databaseName"]
        self.host = db_params["db-host"]
        self.db_path = ""
        gen = c.get_general_params()
        self.day_start = 0.0
        self._hero = None
        self._has_lock = False
        self.printdata = False
        # Read caches for values the HUD asks for once per open table per hand
        # dealt, but which cannot have changed in between; see
        # get_gameinfo_from_hid and database_hud_stats._refresh_hand_1day_ago.
        # Created before resetCache, which is what empties them.
        self._gameinfo_cache: TTLCache = TTLCache(maxsize=GAMEINFO_CACHE_SIZE, ttl=GAMEINFO_CACHE_TTL)
        self._hand_1day_ago_read_at = 0.0
        self.resetCache()
        self.resetBulkCache()
        self._in_transaction = 0
        # Reconnection state (see db_reconnect). The guard collapses nested
        # decorated calls onto a single retry; the deadline throttles reconnect
        # attempts so a database that stays unreachable costs one connect
        # timeout per cooldown window instead of one per query.
        self._reconnect_guard = False
        self._reconnect_blocked_until = 0.0
        self._connection_down_logged = False

        if "day_start" in gen:
            self.day_start = float(gen["day_start"])

        self.sessionTimeout = float(self.import_options["sessionTimeout"])
        self.publicDB = self.import_options["publicDB"]

        # where possible avoid creating new SQL instance by using the global one passed in
        if sql is None:
            self.sql = SQL.Sql(db_server=self.db_server)
        else:
            self.sql = sql

        if autoconnect:
            self._connect_and_configure(c)

    # end def __init__


    def dumpDatabase(self):
        result = "fpdb database dump\nDB version=" + str(DB_VERSION) + "\n\n"

        # tables = self.cursor.execute(self.sql.query["list_tables"])
        # tables = self.cursor.fetchall()
        for table in (
            "Actions",
            "Autorates",
            "Backings",
            "Gametypes",
            "Hands",
            "Boards",
            "BoardFeatures",
            "HandsActions",
            "HandsPlayers",
            "HandsStove",
            "Files",
            "HudCache",
            "Sessions",
            "SessionsCache",
            "TourneysCache",
            "Players",
            "RawHands",
            "RawTourneys",
            "Settings",
            "Sites",
            "TourneyTypes",
            "Tourneys",
            "TourneysPlayers",
        ):
            log.debug(f"table: {table}")
            result += "###################\nTable " + table + "\n###################\n"
            rows = self.cursor.execute(self.sql.query["get" + table])
            rows = self.cursor.fetchall()
            columnNames = self.cursor.description
            if not rows:
                result += "empty table\n"
            else:
                for row in rows:
                    for columnNumber in range(len(columnNames)):
                        if columnNames[columnNumber][0] == "importTime" or columnNames[columnNumber][0] == "styleKey":
                            result += "  " + columnNames[columnNumber][0] + "=ignore\n"
                        else:
                            result += "  " + columnNames[columnNumber][0] + "=" + str(row[columnNumber]) + "\n"
                    result += "\n"
            result += "\n"
        return result

    # end def dumpDatabase

    # could be used by hud to change hud style
    def set_hud_style(self, style) -> None:
        self.hud_style = style


    def connect(
        self,
        backend=None,
        host=None,
        port=None,
        database=None,
        user=None,
        password=None,
        create=False,
    ) -> None:
        """Connects a database with the given parameters."""
        if backend is None:
            msg = "Database backend not defined"
            raise FpdbError(msg)
        self.backend = backend
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.connection = None
        self.cursor = None
        self.hand_inc = 1

        if backend == Database.MYSQL_INNODB:
            self._connect_mysql(host, port, user, password, database)
        elif backend == Database.PGSQL:
            self._connect_postgresql(host, port, user, password, database)
        elif backend == Database.SQLITE:
            database, create = self._connect_sqlite(database, create)
        else:
            raise FpdbError("unrecognised database backend:" + str(backend))

        # Off unless FPDB_DB_PROFILE=1, in which case every statement issued
        # through this connection is counted and attributed (see db_profile).
        # Done here so it survives a reconnect, which comes back through connect().
        self.connection = db_profile.wrap_connection(self.connection, getattr(self.sql, "query", None))

        if self.is_connected():
            self.cursor = self.connection.cursor()
            self.cursor.execute(self.sql.query["set tx level"])
            self.check_version(database=database, create=create)


    def get_cursor(self, connect=False):
        if self.backend == Database.MYSQL_INNODB and os.name == "nt":
            self.connection.ping(True)
        return self.connection.cursor()

    @contextlib.contextmanager
    def worker_connection(self):
        """Context manager for a dedicated worker connection from a bounded pool.

        Limits the number of concurrent connections to avoid hitting
        max_connections on PostgreSQL (and MySQL).

        The connection is always returned to the pool with its transaction
        ended. Workers only read, but a read still opens a transaction, and one
        that is never ended does two things: it leaves the connection in ``idle
        in transaction`` holding read locks for the life of the process --
        pinning autovacuum off Hands and HandsPlayers, and standing in the way
        of anything needing a stronger lock (#249, #271) -- and, when the query
        failed, it hands the next borrower a connection whose transaction is
        already aborted, so every later query on it fails too.
        """
        with Database._worker_pool_lock:
            Database._worker_pools.add(self._worker_conn_pool)
            Database._worker_retired_pools.discard(self._worker_conn_pool)
        conn = None
        slot_acquired = False
        try:
            # The global semaphore bounds checked-out connections, not just
            # newly created ones. Reusing an idle connection must consume the
            # same process-wide capacity or several database instances can
            # exceed the intended four-worker connection bound.
            self._worker_conn_semaphore.acquire()
            slot_acquired = True
            try:
                with Database._worker_pool_lock:
                    conn = self._worker_conn_pool.get_nowait()
                    Database._worker_idle_connections -= 1
            except queue.Empty:
                # An idle connection owned by another Database still occupies
                # a process-wide slot. Evict stale idle pools before waiting
                # for the active-worker slot, so a newly opened study cannot
                # be starved by connections retained by another study.
                self._evict_idle_worker_connections(exclude=self._worker_conn_pool)
                conn = self._create_new_worker_connection()

            yield conn
        finally:
            self._return_worker_connection(conn)
            if slot_acquired:
                self._worker_conn_semaphore.release()

    @classmethod
    def _evict_idle_worker_connections(cls, exclude=None) -> None:
        """Drop idle connections from other pools before opening a new one."""
        with cls._worker_pool_lock:
            for pool in tuple(cls._worker_pools):
                if pool is exclude:
                    continue
                while True:
                    try:
                        conn = pool.get_nowait()
                    except queue.Empty:
                        break
                    cls._worker_idle_connections -= 1
                    with contextlib.suppress(Exception):
                        conn.close()

    def _return_worker_connection(self, conn) -> None:
        """Put a worker connection back, with nothing left open on it.

        A connection whose rollback fails is beyond reuse, so it is dropped
        rather than pooled; the next borrower simply opens a fresh one.
        """
        if conn is None:
            return
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001 - a connection that cannot roll back is not reusable
            log.debug("Discarding a worker connection that could not be rolled back", exc_info=True)
            with contextlib.suppress(Exception):
                conn.close()
            return
        with Database._worker_pool_lock:
            retired = self._worker_conn_pool in Database._worker_retired_pools
            registered = self._worker_conn_pool in Database._worker_pools
            if retired:
                close_connection = True
            elif registered and Database._worker_idle_connections >= Database._worker_idle_limit:
                close_connection = True
            else:
                close_connection = False
                self._worker_conn_pool.put(conn)
                if registered:
                    Database._worker_idle_connections += 1
        if close_connection:
            with contextlib.suppress(Exception):
                conn.close()

    def _create_new_worker_connection(self):
        """Open a dedicated connection for a background worker thread.

        Returns None when no dedicated connection can be built (e.g. SQLite
        ``:memory:``), in which case the worker falls back to the shared
        connection.

        No DBAPI driver used here allows two threads to drive one connection
        concurrently without an application-level lock:

        - sqlite3 (check_same_thread=False) serializes calls but interleaves
          execute/fetchall pairs from the GUI thread and DbWorker threads,
          which deadlocks the GUI on macOS. WAL mode makes one read connection
          per thread safe.
        - psycopg3 is thread-safe at connection level but NOT at cursor level:
          two threads sharing one connection can interleave execute/fetchall.
        - MySQLdb/pymysql has threadsafety=1: connections must NOT be shared
          across threads at all.

        The returned connection is intentionally NOT passed through
        db_profile.wrap_connection: profiling is single-process bookkeeping and
        worker round trips stay attributed to the main connection.
        """
        if self.backend == self.SQLITE:
            return self._create_sqlite_worker_connection()
        if self.backend == self.PGSQL:
            return self._create_postgresql_worker_connection()
        if self.backend == self.MYSQL_INNODB:
            return self._create_mysql_worker_connection()
        return None

    def _create_sqlite_worker_connection(self):
        """Dedicated SQLite connection for a worker thread (WAL mode)."""
        if not self.db_path or self.db_path == ":memory:":
            return None
        import sqlite3

        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            timeout=60.0,
            check_same_thread=False,
        )
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(SQLITE_SYNCHRONOUS_PRAGMA)
        conn.create_function("floor", 1, math.floor)
        conn.create_function("sqrt", 1, math.sqrt)
        tmp = sqlitemath()
        conn.create_function("mod", 2, tmp.mod)
        if use_numpy:
            conn.create_aggregate("variance", 1, VARIANCE)
        return conn

    def _create_postgresql_worker_connection(self):
        """Dedicated PostgreSQL connection for a worker thread."""
        import psycopg

        kwargs = {"dbname": self.database, **PG_NETWORK_KWARGS}
        if self.host not in ("localhost", "127.0.0.1"):
            kwargs.update({"host": self.host, "port": self.port, "user": self.user, "password": self.password})
        try:
            return psycopg.connect(**kwargs)
        except psycopg.OperationalError:
            # Local peer connection failed; retry with explicit credentials.
            return psycopg.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                dbname=self.database,
                **PG_NETWORK_KWARGS,
            )

    def _create_mysql_worker_connection(self):
        """Dedicated MySQL connection for a worker thread."""
        try:
            import MySQLdb
        except ImportError:
            import pymysql

            pymysql.install_as_MySQLdb()
            import MySQLdb

        return MySQLdb.connect(
            **_mysql_connection_kwargs(self.host, self.port, self.user, self.password, self.database)
        )


    def close_worker_pool(self) -> None:
        """Close the connections idling in this database's worker pool.

        An instance method since the pool became one: closing "the" pool from
        the class would have had to pick a database, and there is more than
        one only because they are different databases.
        """
        pool = getattr(self, "_worker_conn_pool", None)
        if pool is None:
            return
        retired_connections = []
        # Retire the identity before draining it, atomically with the queue
        # transition. A worker that returns between the final empty check and
        # the retirement marker must not put an untracked connection back.
        with Database._worker_pool_lock:
            Database._worker_pools.discard(pool)
            Database._worker_retired_pools.add(pool)
        while True:
            try:
                with Database._worker_pool_lock:
                    conn = pool.get_nowait()
                    Database._worker_idle_connections -= 1
            except queue.Empty:
                break
            if conn is not None:
                retired_connections.append(conn)
        for conn in retired_connections:
            with contextlib.suppress(Exception):
                conn.close()


    def set_printdata(self, val) -> None:
        self.printdata = val

    # is get_stats_from_hand slow?
    # Gimick - yes  - reason being that the gametypeid join on hands
    # increases exec time on SQLite and postgres by a factor of 6 to 10
    # method below changed to lookup hand.gametypeid and pass that as
    # a constant to the underlying query.

    # uses query on handsplayers instead of hudcache to get stats on just this session

    # print "session stat_dict =", stat_dict
    # return stat_dict


    def resetCache(self) -> None:
        self.ttold: set[Any] = set()  # TourneyTypes old
        self.ttnew: set[Any] = set()  # TourneyTypes new
        self.wmold: set[Any] = set()  # WeeksMonths old
        self.wmnew: set[Any] = set()  # WeeksMonths new
        self.gtcache = None  # GameTypeId cache
        self.tcache = None  # TourneyId cache
        self.pcache = None  # PlayerId cache
        self.tpcache = None  # TourneysPlayersId cache
        # Read caches keyed by hand id. recreate_tables() comes through here,
        # and it restarts hand ids from 1 -- an entry kept across that would be
        # served for a different hand entirely. Read defensively: resetCache
        # also runs on the transaction-rollback path, and clearing a cache must
        # never be the thing that makes a rollback fail.
        gameinfo_cache = getattr(self, "_gameinfo_cache", None)
        if gameinfo_cache is not None:
            gameinfo_cache.clear()
        self._hand_1day_ago_read_at = 0.0

    def get_last_insert_id(self, cursor=None):
        ret = None
        try:
            if self.backend == self.MYSQL_INNODB:
                ret = self.connection.insert_id()
                if ret < 1 or ret > 999999999:
                    log.warning(
                        f"getLastInsertId(): problem fetching insert_id? ret={ret}",
                    )
                    ret = -1
            elif self.backend == self.PGSQL:
                # some options:
                # currval(hands_id_seq) - use name of implicit seq here
                # lastval() - still needs sequences set up?
                # insert ... returning  is useful syntax (but postgres specific?)
                # see rules (fancy trigger type things)
                c = self.get_cursor()
                ret = c.execute("SELECT lastval()")
                row = c.fetchone()
                if not row:
                    log.warning(
                        f"getLastInsertId(): problem fetching lastval? row={row}",
                    )
                    ret = -1
                else:
                    ret = row[0]
            elif self.backend == self.SQLITE:
                ret = cursor.lastrowid
            else:
                log.error(f"getLastInsertId(): unknown backend: {self.backend}")
                ret = -1
        except Exception:  # intentional broad catch: getLastInsertId logs full traceback then re-raises
            ret = -1
            err = traceback.extract_tb(sys.exc_info()[2])
            log.exception(f"Database get_last_insert_id error: {sys.exc_info()[1]}")
            log.exception("\n".join(f"{e[0]}:{e[1]} {e[2]}" for e in err))
            raise
        return ret


    def analyzeDB(self) -> None:
        """Do whatever the DB can offer to update index/table statistics."""
        stime = time()
        if self.backend in (self.MYSQL_INNODB, self.SQLITE):
            try:
                self.get_cursor().execute(self.sql.query["analyze"])
            except Exception:  # intentional broad catch: analyzeDB (MySQL/SQLite) maintenance best-effort
                log.exception(f"Error during analyze: {sys.exc_info()[1]!s}")
        elif self.backend == self.PGSQL:
            self._pg_set_isolation(0)  # allow analyze to work
            try:
                self.get_cursor().execute(self.sql.query["analyze"])
            except Exception:  # intentional broad catch: analyzeDB (PG) maintenance best-effort
                log.exception(f"Error during analyze: {sys.exc_info()[1]!s}")
            self._pg_set_isolation(1)  # go back to normal isolation level
        self.commit()
        atime = time() - stime
        log.info(f"Analyze took {atime:.1f} seconds")

    # end def analyzeDB

    def vacuumDB(self) -> None:
        """Do whatever the DB can offer to update index/table statistics."""
        stime = time()
        if self.backend in (self.MYSQL_INNODB, self.SQLITE):
            try:
                self.get_cursor().execute(self.sql.query["vacuum"])
            except Exception:  # intentional broad catch: vacuumDB (MySQL/SQLite) maintenance best-effort
                log.exception(f"Error during vacuum: {sys.exc_info()[1]!s}")
        elif self.backend == self.PGSQL:
            self._pg_set_isolation(0)  # allow vacuum to work
            try:
                self.get_cursor().execute(self.sql.query["vacuum"])
            except Exception as e:  # intentional broad catch: vacuumDB (PG) maintenance best-effort
                log.exception(f"Error during vacuum: {e!s}")
            self._pg_set_isolation(1)  # go back to normal isolation level
        self.commit()
        atime = time() - stime
        log.debug(f"Vacuum took {atime:.1f} seconds")

    # end def analyzeDB

    # Start of Hand Writing routines. Idea is to provide a mixture of routines to store Hand data
    # however the calling prog requires. Main aims:
    # - existing static routines from fpdb_simple just modified

    def setThreadId(self, threadid) -> None:
        self.threadId = threadid

    def acquireLock(self, wait=True, retry_time=0.01) -> bool:
        while not self._has_lock:
            cursor = self.get_cursor()
            num = cursor.execute(self.sql.query["switchLockOn"], (True, self.threadId))
            self.commit()
            if self.backend == self.MYSQL_INNODB and num == 0:
                if not wait:
                    return False
                sleep(retry_time)
            else:
                self._has_lock = True
                return True
        return False

    def releaseLock(self) -> None:
        if self._has_lock:
            cursor = self.get_cursor()
            cursor.execute(self.sql.query["switchLockOff"], (False, self.threadId))
            self.commit()
            self._has_lock = False

    def lock_for_insert(self) -> None:
        """Lock tables in MySQL to try to speed inserts up."""
        try:
            self.get_cursor().execute(self.sql.query["lockForInsert"])
        except Exception as e:  # intentional broad catch: lock_for_insert (MySQL) best-effort speed-up
            log.debug(f"Error during lock_for_insert: {e!s}")

    # end def lock_for_insert


    def repair_sequence(self, table: str) -> None:
        """Synchronize a backend identity sequence with the stored row ids."""
        from fpdb_3_legacy import dialects

        dialects.dialect_for_backend(self.backend).repair_sequence(self, table)

    def repair_sequences(self) -> None:
        """Synchronize every backend identity sequence after a data migration."""
        from fpdb_3_legacy import dialects

        dialects.dialect_for_backend(self.backend).repair_sequences(self)

    def updateFile(self, fdata) -> None:
        q = self.sql.query["update_file"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c = self.get_cursor()
        c.execute(q, fdata)


    def nextHandId(self):
        c = self.get_cursor(True)
        if self.backend == self.PGSQL:
            # Hand ids are assigned before the root and child rows are built.
            # Serialize max(id)+1 across importer processes until their current
            # transaction commits, otherwise two live feeds can reserve the
            # same explicit Hands.id.
            c.execute("SELECT pg_advisory_xact_lock(hashtext('fpdb_hands_id_allocator'))")
        c.execute("SELECT max(id) FROM Hands")
        id = c.fetchone()[0]
        if not id:
            id = 0
        id += self.hand_inc
        return id

    def isDuplicate(self, siteId, siteHandNo, heroSeat, publicDB) -> bool:
        q = self.sql.query["isAlreadyInDB"].replace("%s", self.sql.query["placeholder"])
        key: tuple[Any, ...]
        if publicDB:
            key = (siteHandNo, siteId, heroSeat)
            q = q.replace("<heroSeat>", " AND heroSeat=%s").replace(
                "%s",
                self.sql.query["placeholder"],
            )
        else:
            key = (siteHandNo, siteId)
            q = q.replace("<heroSeat>", "")
        if key in self.siteHandNos:
            return True
        c = self.get_cursor()
        c.execute(q, key)
        result = c.fetchall()
        if len(result) > 0:
            return True
        self.siteHandNos.append(key)
        return False

    def insertOrUpdate(self, type, cursor, key, select, insert):
        if type == "players":
            cursor.execute(select, key[:2])
        else:
            cursor.execute(select, key)
        tmp = cursor.fetchone()
        if tmp is None:
            cursor.execute(insert, key)
            result = self.get_last_insert_id(cursor)
        else:
            result = tmp[0]
            if type == "players" and not tmp[2] and key[2]:
                q = "UPDATE Players SET hero=%s WHERE name=%s and siteid=%s"
                q = q.replace("%s", self.sql.query["placeholder"])
                cursor.execute(q, (key[2], key[0], key[1]))
        return result

    def getSqlGameTypeId(self, siteid, game, printdata=False):
        if self.gtcache is None:
            self.gtcache = LambdaDict(lambda key: self.insertGameTypes(key[0], key[1]))

        self.gtprintdata = printdata
        hilo = Card.games[game["category"]][2]

        gtinfo = (
            siteid,
            game["type"],
            game["category"],
            game["limitType"],
            game["currency"],
            game["mix"],
            int(Decimal(game["sb"]) * 100),
            int(Decimal(game["bb"]) * 100),
            game["maxSeats"],
            int(game["ante"] * 100),
            game["buyinType"],
            game["fast"],
            game["newToGame"],
            game["homeGame"],
            game["split"],
        )

        gtinsert = (
            siteid,
            game["currency"],
            game["type"],
            game["base"],
            game["category"],
            game["limitType"],
            hilo,
            game["mix"],
            int(Decimal(game["sb"]) * 100),
            int(Decimal(game["bb"]) * 100),
            int(Decimal(game["bb"]) * 100),
            int(Decimal(game["bb"]) * 200),
            game["maxSeats"],
            int(game["ante"] * 100),
            game["buyinType"],
            game["fast"],
            game["newToGame"],
            game["homeGame"],
            game["split"],
        )

        return self.gtcache[(gtinfo, gtinsert)]
        # NOTE: Using the LambdaDict does the same thing as:
        # if player in self.pcache:
        #    #print "DEBUG: cachehit"
        #    pass
        # else:
        #    self.pcache[player] = self.insertPlayer(player, siteid)
        # result[player] = self.pcache[player]

    def insertGameTypes(self, gtinfo, gtinsert):
        result = None
        c = self.get_cursor()
        q = self.sql.query["getGametypeNL"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c.execute(q, gtinfo)
        tmp = c.fetchone()
        if tmp is None:
            if self.gtprintdata:
                log.debug("######## Gametype ##########")
                import pprint

                pp = pprint.PrettyPrinter(indent=4)
                pp.pprint(gtinsert)
                log.debug("###### End Gametype ########")

            c.execute(
                self.sql.query["insertGameTypes"].replace(
                    "%s",
                    self.sql.query["placeholder"],
                ),
                gtinsert,
            )
            result = self.get_last_insert_id(c)
        else:
            result = tmp[0]
        return result

    # end def getTourneyInfo

    # end def getTourneyTypesIds


    def __del__(self) -> None:
        """Ensure connections are cleaned up when Database object is destroyed."""
        try:
            self.cleanup_connections()
        except Exception:  # intentional broad catch: destructor cleanup must not raise
            log.debug("Database cleanup failed during object destruction", exc_info=True)


# end class Database


def _build_cli_parser():
    """The command-line surface of the Database utility."""
    import argparse

    parser = argparse.ArgumentParser(description="FPDB Database utility")
    parser.add_argument("--test-connection", action="store_true", help="Test database connection")
    parser.add_argument("--rebuild-indexes", action="store_true", help="Drop and recreate all database indexes")
    parser.add_argument("--vacuum", action="store_true", help="Reclaim space and optimize database storage")
    parser.add_argument("--show-stats", action="store_true", help="Show statistics for last hand")
    parser.add_argument("--show-info", action="store_true", help="Show database information")
    parser.add_argument("--interactive", action="store_true", help="Run original interactive test")
    return parser


def _cli_show_info(db_connection) -> None:
    print("\n=== Database Information ===")
    print(f"Backend type: {db_connection.backend}")
    print(f"Database name: {db_connection.database}")
    print(f"Host: {db_connection.host}")


def _cli_show_stats(db_connection) -> None:
    try:
        h = db_connection.get_last_hand()
        if h:
            print(f"\n=== Statistics for Hand {h} ===")
            t0 = time()
            stat_dict = db_connection.get_stats_from_hand(h, "ring")
            t1 = time()

            for p in sorted(stat_dict.keys()):
                print(f"  {p}: {stat_dict[p]}")

            print(f"\nQuery took: {t1 - t0:4.3f} seconds")

            cards = db_connection.get_cards("1")
            if cards:
                print(f"Cards for player 1: {cards}")
        else:
            print("No hands found in database")
    except Exception as e:  # intentional broad catch: CLI top-level show-stats boundary
        print(f"Error retrieving statistics: {e}")


def _cli_interactive(db_connection, config, sql) -> None:
    print("Running original interactive test...")
    log.debug(f"database connection object = {db_connection.connection}")
    db_connection.dropAllIndexes()
    db_connection.createAllIndexes()

    h = db_connection.get_last_hand()
    log.debug(f"last hand = {h}")

    hero = db_connection.get_player_id(config, "PokerStars", "nutOmatic")
    if hero:
        log.debug(f"nutOmatic player_id {hero}")

    if db_connection.backend == 4:
        c = db_connection.get_cursor()
        c.execute("explain query plan " + sql.query["get_table_name"], (h,))
        for row in c.fetchall():
            log.debug(f"Query plan: {row}")

    t0 = time()
    stat_dict = db_connection.get_stats_from_hand(h, "ring")
    t1 = time()
    for p in list(stat_dict.keys()):
        log.debug(f"{p}  {stat_dict[p]}")

    log.debug(f"cards = {db_connection.get_cards('1')}")
    db_connection.close_connection()

    log.debug(f"get_stats took: {t1 - t0:4.3f} seconds")

    print("Press ENTER to continue...")
    sys.stdin.readline()


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = _build_cli_parser()
    args = parser.parse_args(argv)

    if not any(vars(args).values()):
        parser.print_help()
        return 0

    Configuration.set_logfile("fpdb-log.txt")

    try:
        c = Configuration.Config()
        sql = SQL.Sql(db_server="sqlite")
        db_connection = Database(c)
    except Exception as e:  # intentional broad catch: CLI top-level DB connect boundary
        print(f"Error connecting to database: {e}")
        return 1

    if args.test_connection:
        print("Database connection successful \u2713")
        print(f"Backend: {db_connection.backend}")
        print(f"Connection: {db_connection.connection}")

    if args.show_info:
        _cli_show_info(db_connection)

    if args.rebuild_indexes:
        print("Rebuilding indexes and foreign keys...")
        db_connection.rebuild_indexes()
        print("Index rebuild complete \u2713")

    if args.vacuum:
        print("Vacuuming database...")
        db_connection.vacuumDB()
        print("Database vacuum complete \u2713")

    if args.show_stats:
        _cli_show_stats(db_connection)

    if args.interactive:
        _cli_interactive(db_connection, c, sql)

    return 0


if __name__ == "__main__":
    sys.exit(main())
