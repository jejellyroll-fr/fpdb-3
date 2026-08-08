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
import re
import sys
import traceback
from datetime import datetime, timedelta
from decimal import Decimal
from importlib import import_module
from time import sleep, time
from typing import Any

import pytz
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
from fpdb_3_legacy.database_hud_stats import DatabaseHudStatsMixin
from fpdb_3_legacy.database_lambda_dict import LambdaDict
from fpdb_3_legacy.database_players import DatabasePlayersMixin
from fpdb_3_legacy.database_schema import DB_VERSION, DatabaseSchemaMixin

# HANDS_PLAYERS_KEYS moved to database_schema with the DDL that checks those
# columns; re-exported because four test modules import it from Database.
from fpdb_3_legacy.database_schema import HANDS_PLAYERS_KEYS as HANDS_PLAYERS_KEYS
from fpdb_3_legacy.database_tournaments import DatabaseTournamentsMixin
from fpdb_3_legacy.db_reconnect import (
    MYSQL_NETWORK_KWARGS,
    PG_NETWORK_KWARGS,
    RECONNECT_COOLDOWN,
    reconnect_on_connection_loss,
)
from fpdb_3_legacy.Exceptions import (
    FpdbDatabaseError,
    FpdbError,
    FpdbMySQLAccessDenied,
    FpdbMySQLNoDatabase,
    FpdbPostgresqlAccessDenied,
    FpdbPostgresqlNoDatabase,
)
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.table_info import TableInfo

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

#    FreePokerTools modules


if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("database")

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

try:
    # AttributeError guards against a partially bundled numpy: in a frozen
    # build "numpy" can resolve to a namespace package holding only the
    # compiled sub-packages, with none of the top-level functions.
    var = getattr(import_module("numpy"), "var")

    use_numpy = True
except (ImportError, AttributeError):
    log.warning("Not using numpy to define variance in sqlite.", exc_info=True)
    use_numpy = False


# Variance created as sqlite has a bunch of undefined aggregate functions.


class VARIANCE:
    def __init__(self) -> None:
        self.store: list[Any] = []

    def step(self, value) -> None:
        self.store.append(value)

    def finalize(self):
        return float(var(self.store))


class sqlitemath:
    def mod(self, a, b):
        return a % b


def adapt_decimal(d):
    return str(d)


def convert_decimal(s):
    log.debug(f"Converting value: {s}")
    s = s.decode()
    return Decimal(s)


# These are for appendStats. Insert new stats at the right place, because
# SQL needs strict order.

class DatabaseTransaction:
    """Context manager for grouping database operations into a single transaction.

    Nested context managers increment the transaction depth, and only the outermost
    context manager executes the commit or rollback.
    """

    def __init__(self, db) -> None:
        self.db = db

    def __enter__(self) -> "DatabaseTransaction":
        self.db._in_transaction += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.db._in_transaction -= 1
        if exc_type is not None:
            log.warning(f"Transaction rolling back due to exception: {exc_val}")
            try:
                self.db.rollback(force=True)
                # IDs inserted during the failed transaction may already be in
                # the lazy caches. They no longer exist after rollback and must
                # never be reused by the next auto-import cycle.
                self.db.resetCache()
                self.db.resetBulkCache()
            except (
                Exception
            ) as e:  # intentional broad catch: transaction rollback during teardown is best-effort, just log
                log.exception(f"Rollback failed: {e}")
        else:
            if self.db._in_transaction == 0:
                try:
                    self.db.commit(force=True)
                except (
                    Exception
                ) as e:  # intentional broad catch: transaction commit during teardown; rolls back then re-raises
                    log.exception(f"Commit failed: {e}")
                    try:
                        self.db.rollback(force=True)
                        self.db.resetCache()
                        self.db.resetBulkCache()
                    except (
                        Exception
                    ) as roll_err:  # intentional broad catch: rollback after a failed commit is best-effort, just log
                        log.exception(f"Rollback after failed commit also failed: {roll_err}")
                    raise e


class Database(
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

    def connection_params_changed(self, c) -> bool:
        """Return whether ``c`` points at a different database than the live one."""
        db_params = c.get_db_parameters()
        return (
            db_params["db-backend"] != self.backend
            or db_params["db-server"] != self.db_server
            or db_params["db-databaseName"] != self.database
            or db_params["db-host"] != self.host
        )

    def rebind_config(self, c) -> bool:
        """Adopt a freshly parsed config on the open connection, or refuse.

        Reloading the configuration -- which fpdb does before opening most of
        its dialogs -- used to disconnect and reconnect unconditionally. On a
        networked backend that is a connect round trip on the GUI thread, and
        it also throws away the read caches this object keeps for the HUD.
        When the reloaded config still names the same database there is nothing
        to reconnect to, so refresh only the values ``__init__`` derives from
        the config and keep the connection.

        Returns False when the connection is down or the config points
        somewhere else; the caller then builds a new Database as before.
        """
        if not self.is_connected() or self.connection_params_changed(c):
            return False

        self.config = c
        self.import_options = c.get_import_parameters()
        gen = c.get_general_params()
        self.day_start = float(gen["day_start"]) if "day_start" in gen else 0.0
        self.sessionTimeout = float(self.import_options["sessionTimeout"])
        self.publicDB = self.import_options["publicDB"]
        return True

    def _connect_and_configure(self, c) -> None:
        """Open the connection, then set up what needs an open connection."""
        # connect to db
        self.do_connect(c)

        if self.backend == self.PGSQL:
            pass
            # ISOLATION_LEVEL_AUTOCOMMIT     = 0
            # ISOLATION_LEVEL_READ_COMMITTED = 1
            # ISOLATION_LEVEL_SERIALIZABLE   = 2

        if (
            self.backend == self.SQLITE
            and self.database == ":memory:"
            and self.wrongDbVersion
            and self.is_connected()
        ):
            log.info("sqlite/:memory: - creating")
            self.recreate_tables()
            self.wrongDbVersion = False
        elif self.is_connected():
            # Create feature tables added after the original schema so that
            # existing databases keep working (showdown / cashout details).
            self.ensure_feature_tables()

        self.gtcache: Any = None  # GameTypeId cache
        self.tcache: Any = None  # TourneyId cache
        self.pcache: Any = None  # PlayerId cache
        self.tpcache: Any = None  # TourneysPlayersId cache

        # if fastStoreHudCache is true then the hudcache will be build using the limited configuration which ignores date, seats, and position
        self.build_full_hudcache = not self.import_options["fastStoreHudCache"]
        self.cacheSessions = self.import_options["cacheSessions"]
        self.callHud = self.import_options["callFpdbHud"]

        # self.hud_hero_style = 'T'  # Duplicate set of vars just for hero - not used yet.
        # self.hud_hero_hands = 2000 # Idea is that you might want all-time stats for others
        # self.hud_hero_days  = 30   # but last T days or last H hands for yourself

        # vars for hand ids or dates fetched according to above config:
        self.hand_1day_ago = 0  # max hand id more than 24 hrs earlier than now
        self.date_ndays_ago = "d000000"  # date N days ago ('d' + YYMMDD)
        self.h_date_ndays_ago = "d000000"  # date N days ago ('d' + YYMMDD) for hero
        self.date_nhands_ago: dict[Any, Any] = {}  # dates N hands ago per player

        self.saveActions = self.import_options["saveActions"] is not False

        if self.is_connected():
            if not self.wrongDbVersion:
                self.get_sites()
            if self.connection is not None:
                self.connection.rollback()  # release locks taken during setup

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

    def do_connect(self, c) -> None:
        if c is None:
            msg = "Configuration not defined"
            raise FpdbError(msg)

        db = c.get_db_parameters()
        try:
            self.connect(
                backend=db["db-backend"],
                host=db["db-host"],
                port=db["db-port"],
                database=db["db-databaseName"],
                user=db["db-user"],
                password=db["db-password"],
            )
        except Exception:  # intentional broad catch: connect failure marks disconnected then re-raises
            # error during connect
            self.__connected = False
            raise

        db_params = c.get_db_parameters()
        self.import_options = c.get_import_parameters()
        self.backend = db_params["db-backend"]
        self.db_server = db_params["db-server"]
        self.database = db_params["db-databaseName"]
        self.host = db_params["db-host"]
        self.port = db_params["db-port"]

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

    def _connect_mysql(self, host, port, user, password, database) -> None:
        """Open a MySQL connection and read the server's auto-increment step."""
        # Prefer mysqlclient (MySQLdb); fall back to the pure-Python pymysql
        # shim so MySQL works without the system libraries mysqlclient needs.
        try:
            try:
                import MySQLdb
            except ImportError:
                import pymysql

                pymysql.install_as_MySQLdb()
                import MySQLdb
        except ImportError as err:
            raise FpdbDatabaseError(
                "MySQL driver ('pymysql' / 'MySQLdb') is not installed or available in this environment/build. "
                "Please install 'pymysql' or configure SQLite in your database configuration."
            ) from err

        # Note: SQLAlchemy 2.0 removed pool.manage
        # MySQLdb has its own connection pooling, so we don't need it
        try:
            kwargs = {
                "host": host,
                "user": user,
                "passwd": password,
                "db": database,
                "charset": "utf8",
                "use_unicode": True,
                **MYSQL_NETWORK_KWARGS,
            }
            if port:
                kwargs["port"] = int(port)

            self.connection = MySQLdb.connect(**kwargs)
            self.__connected = True
        except MySQLdb.Error as ex:
            if ex.args[0] == 1045:
                raise FpdbMySQLAccessDenied(ex.args[0], ex.args[1])
            if ex.args[0] == 2002 or ex.args[0] == 2003:  # 2002 is no unix socket, 2003 is no tcp socket
                raise FpdbMySQLNoDatabase(ex.args[0], ex.args[1])
            log.exception("UNKNOWN MYSQL ERROR: {ex}")
        c = self.get_cursor()
        c.execute("show variables like 'auto_increment_increment'")
        self.hand_inc = int(c.fetchone()[1])

    def _connect_postgresql(self, host, port, user, password, database) -> None:
        """Open a PostgreSQL connection, preferring a local peer connection."""
        try:
            import psycopg
        except ImportError as err:
            raise FpdbDatabaseError(
                "PostgreSQL driver ('psycopg') is not installed or available in this environment/build. "
                "Please install 'psycopg' or configure SQLite in your database configuration."
            ) from err

        # Note: SQLAlchemy 2.0 removed pool.manage
        # psycopg has its own connection pooling, so we don't need it
        # psycopg3 handles Unicode natively, no need for register_type(UNICODE)
        # psycopg3 has native Decimal support, no adapter registration needed

        # PG_NETWORK_KWARGS bounds the connect itself and arms TCP keepalives on
        # the resulting socket. Without the keepalives a connection to a remote
        # database (typically over a VPN) does not fail when the link drops --
        # it hangs forever inside the kernel's retransmit loop, taking the HUD's
        # event loop and the auto-import worker down with it. libpq ignores the
        # keepalive settings on a local Unix socket, so the peer connection
        # below is unaffected.
        self.__connected = False
        if self.host in ("localhost", "127.0.0.1"):
            try:
                self.connection = psycopg.connect(dbname=database, **PG_NETWORK_KWARGS)
                self.__connected = True
            except psycopg.OperationalError:
                # direct connection failed so try user/pass/... version
                pass

        if not self.is_connected():
            try:
                self.connection = psycopg.connect(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    dbname=database,
                    **PG_NETWORK_KWARGS,
                )
                self.__connected = True
            except Exception as ex:  # intentional broad catch: psycopg connection error inspected and re-raised as a typed FpdbError
                if "Connection refused" in ex.args[0] or (
                    'database "' in ex.args[0] and '" does not exist' in ex.args[0]
                ):
                    raise FpdbPostgresqlNoDatabase(errmsg=ex.args[0])
                if "password authentication" in ex.args[0]:
                    raise FpdbPostgresqlAccessDenied(errmsg=ex.args[0])
                if 'role "' in ex.args[0] and '" does not exist' in ex.args[0]:  # role "fpdb" does not exist
                    raise FpdbPostgresqlAccessDenied(errmsg=ex.args[0])
                msg = ex.args[0]
                log.exception(f"error postgreslq: {msg}")
                raise FpdbError(msg)

    def _connect_sqlite(self, database, create):
        """Open a SQLite database, creating it and its directory when asked.

        Returns the resolved path and create flag, both of which the caller
        passes on to check_version.
        """
        create = True
        import sqlite3

        # Note: SQLAlchemy 2.0 removed pool.manage
        # SQLite handles concurrent connections well natively with proper settings
        # (see check_same_thread=False and timeout settings below)

        if database != ":memory:":
            if not os.path.isdir(self.config.dir_database) and create:
                log.info(f"Creating directory: '{self.config.dir_database}'")
                os.makedirs(self.config.dir_database)
            database = os.path.join(self.config.dir_database, database).replace(
                "\\",
                "/",
            )
        self.db_path = database
        log.info(f"Connecting to SQLite: {self.db_path}")
        if os.path.exists(database) or create:
            self.connection = sqlite3.connect(
                self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                timeout=60.0,  # Increased timeout to prevent connection timeouts
                check_same_thread=False,  # Allow multi-threaded access
            )
            self.__connected = True
            sqlite3.register_converter("bool", lambda x: bool(int(x)))
            sqlite3.register_adapter(bool, lambda x: 1 if x else 0)
            sqlite3.register_converter("decimal", convert_decimal)
            sqlite3.register_adapter(Decimal, adapt_decimal)
            self.connection.create_function("floor", 1, math.floor)
            self.connection.create_function("sqrt", 1, math.sqrt)
            tmp = sqlitemath()
            self.connection.create_function("mod", 2, tmp.mod)
            if use_numpy:
                self.connection.create_aggregate("variance", 1, VARIANCE)
            else:
                log.warning(
                    ("Some database functions will not work without NumPy support"),
                )
            self.cursor = self.connection.cursor()
            self.cursor.execute(
                "PRAGMA temp_store=2",
            )  # use memory for temp tables/indexes
            self.cursor.execute(
                "PRAGMA journal_mode=WAL",
            )  # use memory for temp tables/indexes
            self.cursor.execute(
                "PRAGMA synchronous=0",
            )  # don't wait for file writes to finish
            self.cursor.execute(
                "PRAGMA busy_timeout=60000",
            )  # wait up to 60 seconds for locks
            self.cursor.execute(
                "PRAGMA cache_size=10000",
            )  # increase cache size for better performance
        else:
            raise FpdbError("sqlite database " + database + " does not exist")
        return database, create
    def get_sites(self) -> None:
        self.cursor.execute("SELECT name,id FROM Sites")
        db_sites = dict(self.cursor.fetchall())
        configured_sites = getattr(self.config, "site_ids", {})
        sites = {**configured_sites, **db_sites}
        self.config.set_site_ids(sorted(sites.items(), key=lambda item: (item[1], item[0])))

    def check_version(self, database, create) -> None:
        self.wrongDbVersion = False
        try:
            self.cursor.execute("SELECT * FROM Settings")
            settings = self.cursor.fetchone()
            if settings[0] != DB_VERSION:
                log.error(
                    f"Outdated or too new database version ({settings[0]}). Please recreate tables.",
                )
                self.wrongDbVersion = True
        except Exception:  # intentional broad catch: settings-table read failure triggers cross-backend table recreate
            if database != ":memory:":
                if create:
                    # print (("Failed to read settings table.") + " - " + ("Recreating tables."))
                    log.info("Failed to read settings table...Recreating tables.")
                    self.recreate_tables()
                    self.check_version(database=database, create=False)
                else:
                    # print (("Failed to read settings table.") + " - " + ("Please recreate tables."))
                    log.info(
                        ("Failed to read settings table...Please recreate tables."),
                    )
                    self.wrongDbVersion = True
            else:
                self.wrongDbVersion = True

    # end def connect

    def _pg_set_isolation(self, level: int) -> None:
        """psycopg2/psycopg3 compatibility for the old ``set_isolation_level(int)``.

        Level 0 meant autocommit (needed around DDL such as CREATE/DROP INDEX,
        VACUUM and ANALYZE) and 1 meant a normal transaction. The psycopg2/psycopg3
        compatibility now lives in the Dialect; this maps the old integer onto its
        ``set_autocommit`` flag.
        """
        from fpdb_3_legacy import dialects

        dialects.dialect_for_backend(self.backend).set_autocommit(self.connection, level == 0)

    def transaction(self) -> DatabaseTransaction:
        """Return a transaction context manager for this database."""
        return DatabaseTransaction(self)

    def commit(self, force: bool = False) -> None:
        if self._in_transaction > 0 and not force:
            log.debug("Database.commit: deferred because we are inside a transaction block")
            return
        if self.backend != self.SQLITE:
            self.connection.commit()
        else:
            # sqlite commits can fail because of shared locks on the database (SQLITE_BUSY)
            # re-try commit if it fails in case this happened
            maxtimes = 5
            pause = 1
            ok = False
            for i in range(maxtimes):
                try:
                    self.connection.commit()
                    # log.debug(("commit finished ok, i = ")+str(i))
                    ok = True
                except Exception as e:  # intentional broad catch: sqlite commit retried on transient SQLITE_BUSY lock
                    log.exception(f"commit {i} failed: info={sys.exc_info()}, value={e}")
                    sleep(pause)
                if ok:
                    break
            if not ok:
                log.error("commit failed")
                msg = "sqlite commit failed"
                raise FpdbError(msg)

    def rollback(self, force: bool = False) -> None:
        if self._in_transaction > 0 and not force:
            log.debug("Database.rollback: deferred because we are inside a transaction block")
            return
        self.connection.rollback()

    def connected(self):
        """Now deprecated, use is_connected() instead."""
        return self.__connected

    def is_connected(self):
        return self.__connected

    def get_cursor(self, connect=False):
        if self.backend == Database.MYSQL_INNODB and os.name == "nt":
            self.connection.ping(True)
        return self.connection.cursor()

    def close_connection(self) -> None:
        if getattr(self, "connection", None):
            self.connection.close()
            self.connection = None
        self.__connected = False

    def _close_cursor_quietly(self) -> None:
        cursor = getattr(self, "cursor", None)
        if not cursor:
            return
        with contextlib.suppress(Exception):
            cursor.close()
        self.cursor = None

    def disconnect(self, due_to_error=False) -> None:
        """Disconnects the DB (rolls back if param is true, otherwise commits."""
        # Guarded like close_connection and _close_cursor_quietly below: a
        # database closed once already has no connection to commit, and calling
        # disconnect twice -- which shutdown paths do -- should be a no-op
        # rather than an AttributeError on the way out.
        if self.connection is not None:
            if due_to_error:
                self.connection.rollback()
            else:
                self.connection.commit()
        self._close_cursor_quietly()
        self.close_connection()
        self.__connected = False

    def reconnect(self, due_to_error=False) -> None:
        """Reconnects the DB."""
        self.disconnect(due_to_error)
        # Keyword arguments on purpose: connect() takes (backend, host, port,
        # database, user, password), so the positional call this used to make
        # silently passed the database as the port and the user as the database.
        self.connect(
            backend=self.backend,
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
        )

    def _force_disconnect(self) -> None:
        """Drop the connection without touching it, for use after it has died.

        ``disconnect()`` commits or rolls back on the way out, which is exactly
        what a broken socket cannot do: the recovery path would raise inside its
        own cleanup and never get as far as reconnecting.
        """
        self._close_cursor_quietly()
        with contextlib.suppress(Exception):
            if self.connection is not None:
                self.connection.close()
        self.connection = None
        self.__connected = False

    def connection_is_alive(self) -> bool:
        """Check the connection with a round trip to the server.

        Cheap, but not free -- it is a real query, so callers should use it to
        check once per work cycle rather than once per statement. Query paths
        detect a dead connection reactively instead, via
        ``reconnect_on_connection_loss``.
        """
        if not self.is_connected() or self.connection is None:
            return False
        if self.backend == self.SQLITE:
            return True
        try:
            c = self.connection.cursor()
            c.execute("SELECT 1")
            c.fetchone()
            c.close()
        except Exception as exc:  # intentional broad catch: any failure here means the connection is unusable
            log.debug("Connection liveness check failed: %s", exc)
            return False
        return True

    def recover_connection(self) -> bool:
        """Re-open a connection that has been lost, at most once per cooldown.

        Returns:
            True when a usable connection is available afterwards.

        A database that stays unreachable -- the VPN is still down -- must stay
        cheap to ask about: without the cooldown every HUD hand would pay a full
        connect timeout, recreating the stall this whole mechanism exists to
        remove. Recovery happens on the first query after the link returns.
        """
        if self.backend == self.SQLITE:
            return self.is_connected()

        now = time()
        if now < self._reconnect_blocked_until:
            log.debug(
                "Skipping reconnect attempt, still in cooldown for %.1fs",
                self._reconnect_blocked_until - now,
            )
            return False

        self._force_disconnect()
        try:
            self.reconnect(due_to_error=True)
        except Exception as exc:  # intentional broad catch: any connect failure means we stay offline and retry later
            self._reconnect_blocked_until = time() + RECONNECT_COOLDOWN
            if not self._connection_down_logged:
                # Log the outage once, then stay quiet: the auto-import retries
                # every few seconds and would otherwise flood the log.
                log.error("Database is unreachable, will keep retrying: %s", exc)
                self._connection_down_logged = True
            else:
                log.debug("Reconnect attempt failed: %s", exc)
            return False

        self._reconnect_blocked_until = 0.0
        if self._connection_down_logged:
            log.info("Database connection re-established.")
            self._connection_down_logged = False
        return self.is_connected()

    def ensure_connection(self) -> bool:
        """Make sure the connection is usable before starting a unit of work.

        Returns:
            True when the caller may proceed to query the database.
        """
        if self.connection_is_alive():
            return True
        if not self._connection_down_logged:
            log.warning("Database connection is not usable; attempting to reconnect.")
        return self.recover_connection()

    def get_backend_name(self) -> str:
        """Returns the name of the currently used backend."""
        if self.backend == 2:
            return "MySQL InnoDB"
        if self.backend == 3:
            return "PostgreSQL"
        if self.backend == 4:
            return "SQLite"
        msg = "invalid backend"
        raise FpdbError(msg)

    def get_db_info(self):
        return (self.host, self.database, self.user, self.password)

    @reconnect_on_connection_loss
    def get_table_name(self, hand_id):
        c = self.connection.cursor()
        c.execute(self.sql.query["get_table_name"], (hand_id,))
        return c.fetchone()

    @reconnect_on_connection_loss
    def get_table_info(self, hand_id):
        c = self.connection.cursor()
        c.execute(self.sql.query["get_table_name"], (hand_id,))
        row = c.fetchone()
        if row is None:
            # Hand not yet committed to the DB (race between the HUD reading the
            # hand id from stdin and the importer writing the row). Let the caller
            # skip and retry on a later notification instead of crashing.
            log.debug("No table info found yet for hand %s", hand_id)
            return None
        # The query selects the eight historical columns first, so the row
        # maps onto TableInfo's leading fields; anything added to the SELECT
        # is read by name here rather than shifting a caller's index.
        limit_type = row[8] if len(row) > 8 else "all"
        table_info = list(row[:8])
        if row[3] == "ring":  # cash game
            return TableInfo.coerce([*table_info, None, None, None, limit_type])
        # tournament
        table_parts = re.split(" ", row[0], maxsplit=1)
        if len(table_parts) == 2:
            tour_no, tab_no = table_parts
        else:
            # Native/HTTP captures can know that a hand is a tournament before
            # the lobby metadata arrives.  In that case the physical table id
            # is also the best stable tournament key; keep the HUD operational
            # instead of raising while parsing the legacy "<tour> <table>"
            # storage convention.
            tour_no = tab_no = str(row[0])
            log.warning(
                "Tournament hand %s has unqualified tableName %r; using it for both tour and table ids",
                hand_id,
                row[0],
            )
        table_info.append(tour_no)
        table_info.append(tab_no)

        # Query tournament name
        tourney_name = None
        try:
            ph = self.sql.query.get("placeholder", "%s")
            q = f"SELECT tourneyName FROM Tourneys WHERE siteTourneyNo = {ph}"
            c.execute(q, (int(tour_no),))
            trow = c.fetchone()
            if trow:
                tourney_name = trow[0]
        except Exception:
            log.exception("Error querying tourneyName for siteTourneyNo=%s", tour_no)
            self._rollback_after_failed_read()

        table_info.append(tourney_name)
        return TableInfo.coerce([*table_info, limit_type])

    def get_last_hand(self):
        c = self.connection.cursor()
        c.execute(self.sql.query["get_last_hand"])
        row = c.fetchone()
        return row[0]

    def get_xml(self, hand_id):
        c = self.connection.cursor()
        c.execute(self.sql.query["get_xml"], (hand_id))
        row = c.fetchone()
        return row[0]

    def get_recent_hands(self, last_hand):
        c = self.connection.cursor()
        c.execute(self.sql.query["get_recent_hands"], {"last_hand": last_hand})
        return c.fetchall()

    def get_gameinfo_from_hid(self, hand_id):
        """Return the gametype of a hand, as Hand.hand_factory wants it.

        Cached: a hand's game is settled when the hand is written and never
        changes afterwards, while the HUD asks for it once per open table per
        hand dealt -- measurably the joint second-largest source of round trips
        (see tools/measure_hud_round_trips.py), which over a VPN is pure
        latency for an answer that cannot have moved.
        """
        cached = self._gameinfo_cache.get(hand_id)
        if cached is not None:
            return cached

        # returns a gameinfo (gametype) dictionary suitable for passing
        # to Hand.hand_factory
        c = self.connection.cursor()
        q = self.sql.query["get_gameinfo_from_hid"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c.execute(q, (hand_id,))
        row = c.fetchone()

        if row is None:
            # Not cached: the hand may simply not be committed yet, and caching
            # the miss would keep answering "no such hand" after it arrives.
            log.warning(f"No game info found for hand ID {hand_id}")
            return None

        gameinfo = {
            "sitename": row[0],
            "category": row[1],
            "base": row[2],
            "type": row[3],
            "limitType": row[4],
            "hilo": row[5],
            "sb": row[6],
            "bb": row[7],
            "sbet": row[8],
            "bbet": row[9],
            "currency": row[10],
            "gametypeId": row[11],
            "split": row[12],
        }
        self._gameinfo_cache[hand_id] = gameinfo
        return gameinfo

    #   Query 'get_hand_info' does not exist, so it seems
    #    def get_hand_info(self, new_hand_id):
    #        c = self.connection.cursor()
    #        c.execute(self.sql.query['get_hand_info'], new_hand_id)
    #        return c.fetchall()

    def getHandCount(self):
        c = self.connection.cursor()
        c.execute(self.sql.query["getHandCount"])
        return c.fetchone()[0]

    # end def getHandCount

    def getTourneyCount(self):
        c = self.connection.cursor()
        c.execute(self.sql.query["getTourneyCount"])
        return c.fetchone()[0]

    # end def getTourneyCount

    def getTourneyTypeCount(self):
        c = self.connection.cursor()
        c.execute(self.sql.query["getTourneyTypeCount"])
        return c.fetchone()[0]

    # end def getTourneyCount

    def getSiteTourneyNos(self, site):
        c = self.connection.cursor()
        q = self.sql.query["getSiteId"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c.execute(q, (site,))
        siteid = c.fetchone()[0]
        q = self.sql.query["getSiteTourneyNos"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c.execute(q, (siteid,))
        alist = []
        for row in c.fetchall():
            alist.append(row)
        return alist

    def get_actual_seat(self, hand_id, name):
        c = self.connection.cursor()
        c.execute(self.sql.query["get_actual_seat"], (hand_id, name))
        row = c.fetchone()
        return row[0]

    @reconnect_on_connection_loss
    def get_cards(self, hand):
        """Get and return the cards for each player in the hand."""
        cards = {}  # dict of cards, the key is the seat number,
        # the value is a tuple of the players cards
        # example: {1: (0, 0, 20, 21, 22, 0 , 0)}
        c = self.connection.cursor()
        c.execute(self.sql.query["get_cards"], [hand])
        for row in c.fetchall():
            cards[row[0]] = row[1:]
        return cards

    def _rollback_after_failed_read(self) -> None:
        """Clear an aborted transaction left by a best-effort HUD read.

        Under PostgreSQL a single failed statement blocks every later query on
        the connection until an explicit ROLLBACK, so a swallowed read error
        would otherwise resurface as InFailedSqlTransaction in unrelated code.
        """
        try:
            self.connection.rollback()
        except Exception:
            log.debug("rollback after failed read did not succeed")

    def get_hand_positions(self, hand):
        """Return {playerId: position} for a hand, for position-conditional HUD panels.

        Position values are as stored by DerivedStats in HandsPlayers.position:
        0 = button, 'S' = small blind, 'B' = big blind, 1.. = seats after the BB.
        """
        positions = {}
        try:
            ph = self.sql.query.get("placeholder", "%s")
            q = "SELECT playerId, position FROM HandsPlayers WHERE handId = %s".replace("%s", ph)
            c = self.connection.cursor()
            c.execute(q, (hand,))
            for row in c.fetchall():
                # int keys, so `pid in stat_dict` in _merge_positions matches.
                positions[row[0]] = row[1]
        except Exception:
            log.exception("get_hand_positions failed for hand %s", hand)
            self._rollback_after_failed_read()
        return positions



    @reconnect_on_connection_loss
    def get_common_cards(self, hand):
        """Get and return the community cards for the specified hand."""
        cards = {}
        c = self.connection.cursor()
        c.execute(self.sql.query["get_common_cards"], [hand])
        #        row = c.fetchone()
        cards["common"] = c.fetchone()
        return cards

    def get_action_from_hand(self, hand_no):
        action: list[list[Any]] = [[], [], [], [], []]
        c = self.connection.cursor()
        c.execute(self.sql.query["get_action_from_hand"], (hand_no,))
        for row in c.fetchall():
            street = row[0]
            act = row[1:]
            action[street].append(act)
        return action

    def get_winners_from_hand(self, hand):
        """Returns a hash of winners:amount won, given a hand number."""
        winners = {}
        c = self.connection.cursor()
        c.execute(self.sql.query["get_winners_from_hand"], (hand,))
        for row in c.fetchall():
            winners[row[0]] = row[1]
        return winners

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



    def get_site_id(self, site):
        c = self.get_cursor()
        c.execute(self.sql.query["getSiteId"], (site,))
        return c.fetchall()

    def get_player_id_by_name(self, player_name: str) -> int | None:
        """Retrieve database player ID by player screen name."""
        try:
            c = self.get_cursor()
            c.execute(self.sql.query["get_player_id_by_name"], (player_name,))
            row = c.fetchone()
            return int(row[0]) if row else None
        except Exception:
            log.exception("get_player_id_by_name failed for player %s", player_name)
            self._rollback_after_failed_read()
            return None

    def get_player_stats_by_name(self, player_name: str, game_type: str = "ring") -> dict[str, Any]:
        """Fetch accumulated lifetime HUD stats for a player screen name."""
        player_id = self.get_player_id_by_name(player_name)
        if player_id is None:
            return {"screen_name": player_name, "n": 0}
        try:
            c = self.get_cursor()
            c.execute(self.sql.query["get_player_stats_by_name"], (player_id,))
            row = c.fetchone()
            if row:
                return {
                    "player_id": player_id,
                    "screen_name": player_name,
                    "n": row[0] or 0,
                    "vpip": float(row[1] or 0),
                    "pfr": float(row[2] or 0),
                    "three_B": float(row[3] or 0),
                    "f_3bet": float(row[4] or 0),
                    "cb1": float(row[5] or 0),
                    "f_cb1": float(row[6] or 0),
                    "wtsd": float(row[7] or 0),
                    "profit100": float(row[8] or 0),
                }
        except Exception:
            log.debug("HudCache query fallback for player %s", player_name)
            self._rollback_after_failed_read()
        return {"player_id": player_id, "screen_name": player_name, "n": 0}

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




    @staticmethod
    def _apply_tourney_clauses(query, type):
        """Fill the three tourney placeholders, or blank them for ring games."""
        if type == "tour":
            query = query.replace("<tourney_insert_clause>", ",tourneyTypeId")
            query = query.replace("<tourney_select_clause>", ",t.tourneyTypeId")
            query = query.replace("<tourney_group_clause>", ",t.tourneyTypeId")
        else:
            query = query.replace("<tourney_insert_clause>", "")
            query = query.replace("<tourney_select_clause>", "")
            query = query.replace("<tourney_group_clause>", "")
        return query

    def _statscache_hudcache(self, query, type):
        """Fill the rebuild template for HudCache, whose key carries the position."""
        insert = """HudCache
            (gametypeId
            ,playerId
            ,seats
            ,position
            <tourney_insert_clause>
            ,styleKey"""

        select = """h.gametypeId
                  ,hp.playerId
                  ,h.seats as seat_num
                  <hc_position>
                  <tourney_select_clause>
                  <styleKey>"""

        group = """h.gametypeId
                    ,hp.playerId
                    ,seat_num
                    ,hc_position
                    <tourney_group_clause>
                    <styleKeyGroup>"""

        query = query.replace("<insert>", insert)
        query = query.replace("<select>", select)
        query = query.replace("<group>", group)
        query = query.replace("<sessions_join_clause>", "")

        if self.build_full_hudcache:
            query = query.replace(
                "<hc_position>",
                """,case when hp.position = 'B' then 'B'
                        when hp.position = 'S' then 'S'
                        when hp.position = '0' then 'D'
                        when hp.position = '1' then 'C'
                        when hp.position = '2' then 'M'
                        when hp.position = '3' then 'M'
                        when hp.position = '4' then 'M'
                        when hp.position = '5' then 'E'
                        when hp.position = '6' then 'E'
                        when hp.position = '7' then 'E'
                        when hp.position = '8' then 'E'
                        when hp.position = '9' then 'E'
                        else 'E'
                   end                                            as hc_position""",
            )
            if self.backend == self.PGSQL:
                query = query.replace(
                    "<styleKey>",
                    ",'d' || to_char(h.startTime, 'YYMMDD')",
                )
                query = query.replace(
                    "<styleKeyGroup>",
                    ",to_char(h.startTime, 'YYMMDD')",
                )
            elif self.backend == self.SQLITE:
                query = query.replace(
                    "<styleKey>",
                    ",'d' || substr(strftime('%Y%m%d', h.startTime),3,7)",
                )
                query = query.replace(
                    "<styleKeyGroup>",
                    ",substr(strftime('%Y%m%d', h.startTime),3,7)",
                )
            elif self.backend == self.MYSQL_INNODB:
                query = query.replace(
                    "<styleKey>",
                    ",date_format(h.startTime, 'd%y%m%d')",
                )
                query = query.replace(
                    "<styleKeyGroup>",
                    ",date_format(h.startTime, 'd%y%m%d')",
                )
        else:
            query = query.replace(
                "<hc_position>",
                """,case when hp.position = 'B' then 'B'
                        when hp.position = 'S' then 'S'
                        when hp.position = '0' then 'D'
                        when hp.position = '1' then 'C'
                        when hp.position = '2' then 'M'
                        when hp.position = '3' then 'M'
                        when hp.position = '4' then 'M'
                        when hp.position = '5' then 'E'
                        when hp.position = '6' then 'E'
                        when hp.position = '7' then 'E'
                        when hp.position = '8' then 'E'
                        when hp.position = '9' then 'E'
                        else 'E'
                   end                                            as hc_position""",
            )
            query = query.replace("<styleKey>", ",'A000000' as styleKey")
            query = query.replace("<styleKeyGroup>", ",styleKey")

        query = self._apply_tourney_clauses(query, type)

        query = query.replace("<hero_where>", "")
        query = query.replace("<hero_join>", "")
        return query

    def _statscache_cardscache(self, query, type):
        """Fill the rebuild template for CardsCache, keyed by starting hand."""
        insert = """CardsCache
            (weekId
            ,monthId
            ,gametypeId
            <tourney_insert_clause>
            ,playerId
            ,startCards"""

        select = """s.weekId
                  ,s.monthId
                  ,h.gametypeId
                  <tourney_select_clause>
                  ,hp.playerId
                  ,hp.startCards"""

        group = """s.weekId
                    ,s.monthId
                    ,h.gametypeId
                    <tourney_group_clause>
                    ,hp.playerId
                    ,hp.startCards"""

        query = query.replace("<insert>", insert)
        query = query.replace("<select>", select)
        query = query.replace("<group>", group)
        query = query.replace("<hero_join>", "")
        query = query.replace(
            "<sessions_join_clause>",
            """INNER JOIN Sessions s ON (s.id = h.sessionId)
            INNER JOIN Players p ON (hp.playerId = p.id)""",
        )
        query = query.replace("<hero_where>", "")

        query = self._apply_tourney_clauses(query, type)
        return query

    def _statscache_positionscache(self, query, type):
        """Fill the rebuild template for PositionsCache, keyed by seat and position."""
        insert = """PositionsCache
            (weekId
            ,monthId
            ,gametypeId
            <tourney_insert_clause>
            ,playerId
            ,seats
            ,maxPosition
            ,position"""

        select = """s.weekId
                  ,s.monthId
                  ,h.gametypeId
                  <tourney_select_clause>
                  ,hp.playerId
                  ,h.seats
                  ,h.maxPosition
                  ,hp.position"""

        group = """s.weekId
                    ,s.monthId
                    ,h.gametypeId
                    <tourney_group_clause>
                    ,hp.playerId
                    ,h.seats
                    ,h.maxPosition
                    ,hp.position"""

        query = query.replace("<insert>", insert)
        query = query.replace("<select>", select)
        query = query.replace("<group>", group)
        query = query.replace("<hero_join>", "")
        query = query.replace(
            "<sessions_join_clause>",
            """INNER JOIN Sessions s ON (s.id = h.sessionId)
            INNER JOIN Players p ON (hp.playerId = p.id)""",
        )
        query = query.replace("<hero_where>", "")

        query = self._apply_tourney_clauses(query, type)
        return query

    def replace_statscache(self, type, table, query):
        if table == "HudCache":
            return self._statscache_hudcache(query, type)
        if table == "CardsCache":
            return self._statscache_cardscache(query, type)
        if table == "PositionsCache":
            return self._statscache_positionscache(query, type)
        return query

    def _rebuild_prepare_heroes(self, h_start, v_start):
        """Resolve the owner's player ids and the two rebuild start dates."""
        # stime = time()
        # derive list of program owner's player ids
        self.hero = {}  # name of program owner indexed by site id
        self.hero_ids: Any = {
            "dummy": -53,
            "dummy2": -52,
        }  # playerid of owner indexed by site id
        # make sure at least two values in list
        # so that tuple generation creates doesn't use
        # () or (1,) style
        if not h_start and not v_start:
            self.hero_ids = None
        else:
            for site in self.config.get_supported_sites():
                result = self.get_site_id(site)
                if result:
                    site_id = result[0][0]
                    self.hero[site_id] = self.config.supported_sites[site].screen_name
                    for idx, p_id in enumerate(self.get_hero_player_ids(site)):
                        self.hero_ids[f"{site_id}_{idx}"] = int(p_id)

            if not h_start:
                h_start = self.hero_hudstart_def
            if not v_start:
                v_start = self.villain_hudstart_def
        return h_start, v_start

    def _rebuild_ring_cache(self, table, h_start, v_start, wmid) -> None:
        """Rebuild the cash half of a statistics cache."""
        if self.hero_ids is None:
            if wmid:
                where = "WHERE g.type = 'ring' AND weekId = {} and monthId = {}<hero_where>".format(*wmid)
            else:
                where = "WHERE g.type = 'ring'<hero_where>"
        else:
            where = (
                "where (((    hp.playerId not in "
                + str(tuple(self.hero_ids.values()))
                + "       and h.startTime > '"
                + v_start
                + "')"
                + "   or (    hp.playerId in "
                + str(tuple(self.hero_ids.values()))
                + "       and h.startTime > '"
                + h_start
                + "'))"
                + "   AND hp.tourneysPlayersId IS NULL)"
            )
        rebuild_sql_cash = self.sql.query["rebuildCache"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        rebuild_sql_cash = rebuild_sql_cash.replace("<tourney_join_clause>", "")
        rebuild_sql_cash = rebuild_sql_cash.replace("<where_clause>", where)
        rebuild_sql_cash = self.replace_statscache("ring", table, rebuild_sql_cash)
        # print rebuild_sql_cash
        self.get_cursor().execute(rebuild_sql_cash)
        self.commit()
        # print ("Rebuild cache(cash) took %.1f seconds") % (time() - stime,)

    def _rebuild_tourney_cache(self, table, h_start, v_start, ttid, wmid) -> None:
        """Rebuild the tournament half of a statistics cache."""
        if ttid:
            where = f"WHERE t.tourneyTypeId = {ttid}<hero_where>"
        elif self.hero_ids is None:
            if wmid:
                where = "WHERE g.type = 'tour' AND weekId = {} and monthId = {}<hero_where>".format(*wmid)
            else:
                where = "WHERE g.type = 'tour'<hero_where>"
        else:
            where = (
                "where (((    hp.playerId not in "
                + str(tuple(self.hero_ids.values()))
                + "       and h.startTime > '"
                + v_start
                + "')"
                + "   or (    hp.playerId in "
                + str(tuple(self.hero_ids.values()))
                + "       and h.startTime > '"
                + h_start
                + "'))"
                + "   AND hp.tourneysPlayersId >= 0)"
            )
        rebuild_sql_tourney = self.sql.query["rebuildCache"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        rebuild_sql_tourney = rebuild_sql_tourney.replace(
            "<tourney_join_clause>",
            """INNER JOIN Tourneys t ON (t.id = h.tourneyId)""",
        )
        rebuild_sql_tourney = rebuild_sql_tourney.replace("<where_clause>", where)
        rebuild_sql_tourney = self.replace_statscache(
            "tour",
            table,
            rebuild_sql_tourney,
        )
        # print rebuild_sql_tourney
        self.get_cursor().execute(rebuild_sql_tourney)
        self.commit()
        # print ("Rebuild hudcache took %.1f seconds") % (time() - stime,)

    def rebuild_cache(
        self,
        h_start=None,
        v_start=None,
        table="HudCache",
        ttid=None,
        wmid=None,
    ) -> None:
        """Clears hudcache and rebuilds from the individual handsplayers records."""
        h_start, v_start = self._rebuild_prepare_heroes(h_start, v_start)

        if not ttid and not wmid:
            self.get_cursor().execute(self.sql.query[f"clear{table}"])
            self.commit()

        if not ttid:
            self._rebuild_ring_cache(table, h_start, v_start, wmid)

        self._rebuild_tourney_cache(table, h_start, v_start, ttid, wmid)

    # end def rebuild_cache

    def update_timezone(self, tz_name) -> None:
        select_W = self.sql.query["select_W"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        select_M = self.sql.query["select_M"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        insert_W = self.sql.query["insert_W"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        insert_M = self.sql.query["insert_M"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        update_WM_S = self.sql.query["update_WM_S"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        c = self.get_cursor()
        c.execute("SELECT id, sessionStart, weekId wid, monthId mid FROM Sessions")
        sessions = self.fetchallDict(c, ["id", "sessionStart", "wid", "mid"])
        for s in sessions:
            utc_start = pytz.utc.localize(s["sessionStart"])
            tz = pytz.timezone(tz_name)
            loc_tz = utc_start.astimezone(tz).strftime("%z")
            offset = timedelta(
                hours=int(loc_tz[:-2]),
                minutes=int(loc_tz[0] + loc_tz[-2:]),
            )
            local = s["sessionStart"] + offset
            monthStart = datetime(local.year, local.month, 1)
            weekdate = datetime(local.year, local.month, local.day)
            weekStart = weekdate - timedelta(days=weekdate.weekday())
            wid = self.insertOrUpdate("weeks", c, (weekStart,), select_W, insert_W)
            mid = self.insertOrUpdate("months", c, (monthStart,), select_M, insert_M)
            if wid != s["wid"] or mid != s["mid"]:
                row = [wid, mid, s["id"]]
                c.execute(update_WM_S, row)
                self.wmold.add((s["wid"], s["mid"]))
                self.wmnew.add((wid, mid))
        self.commit()
        self.cleanUpWeeksMonths()


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





    def updateTourneysSessions(self) -> None:
        if self.tbulk:
            q_update_sessions = self.sql.query["updateTourneysSessions"].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            c = self.get_cursor()
            for t, sid in list(self.tbulk.items()):
                c.execute(q_update_sessions, (sid, t))
                self.commit()






    def get_hands_showdown(self, hand_id) -> dict:
        """Return {player_name: (combo, cards)} for a hand, or {} if none/absent.

        Tolerates databases created before the HandsShowdown table existed.
        """
        result = {}
        try:
            c = self.get_cursor()
            c.execute(self.sql.query["get_hands_showdown"], (hand_id,))
            for name, combo, cards in c.fetchall():
                result[name] = (combo, cards)
        except Exception:  # noqa: BLE001 - missing table / legacy DB: no showdown info.
            return {}
        return result


    def get_hands_cashout(self, hand_id) -> dict:
        """Return {player_name: (amount, fee)} for a hand, or {} if none/absent."""
        result = {}
        try:
            c = self.get_cursor()
            c.execute(self.sql.query["get_hands_cashout"], (hand_id,))
            for name, amount, fee in c.fetchall():
                result[name] = (amount, fee)
        except Exception:  # noqa: BLE001 - missing table / legacy DB: no cashout info.
            return {}
        return result

    def get_hands_splash(self, hand_id) -> dict:
        """Return {player_name: cents} of splash collected, or {} if none/absent."""
        result = {}
        try:
            c = self.get_cursor()
            c.execute(self.sql.query["get_hands_splash"], (hand_id,))
            for name, amount in c.fetchall():
                result[name] = amount
        except Exception:  # noqa: BLE001 - column absent on a database predating the splash work.
            self._rollback_after_failed_read()
            return {}
        return result

    def get_id(self, file):
        q = self.sql.query["get_id"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c = self.get_cursor()
        c.execute(q, (file,))
        id = c.fetchone()
        if not id:
            return 0
        return id[0]


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



    def fetchallDict(self, cursor, desc):
        data = cursor.fetchall()
        if not data:
            return []
        results: list[dict[Any, Any]] = [{} for _ in data]
        for i in range(len(data)):
            for n in range(len(desc)):
                results[i][desc[n]] = data[i][n]
        return results

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

    def _clear_period_caches(self, cursor, wid, mid) -> None:
        """Drop the CardsCache and PositionsCache rows of one week/month pair."""
        for t in ("CardsCache", "PositionsCache"):
            statement = f"clear{t}WeeksMonths"
            clear = self.sql.query[statement].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            cursor.execute(clear, (wid, mid))
        self.commit()

    def _delete_orphan_periods(self, cursor, ids, select_query, delete_query) -> None:
        """Remove week or month rows no session points at any more."""
        for period_id in ids:
            cursor.execute(select_query, (period_id,))
            if not cursor.fetchone():
                cursor.execute(delete_query, (period_id,))
                self.commit()

    def _rebuild_period_caches(self, cursor) -> None:
        """Rebuild the per-period caches for every pair the cleanup touched."""
        wmids = set()
        for t in ("CardsCache", "PositionsCache"):
            statement = f"fetchNew{t}WeeksMonths"
            fetch = self.sql.query[statement].replace(
                "%s",
                self.sql.query["placeholder"],
            )
            cursor.execute(fetch)
            for wid, mid in cursor.fetchall():
                wmids.add((wid, mid))
        for wmid in wmids:
            for t in ("CardsCache", "PositionsCache"):
                self.rebuild_cache(None, None, t, None, wmid)

    def cleanUpWeeksMonths(self) -> None:
        if not (self.cacheSessions and self.wmold):
            return
        selectWeekId = self.sql.query["selectSessionWithWeekId"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        selectMonthId = self.sql.query["selectSessionWithMonthId"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        deleteWeekId = self.sql.query["deleteWeekId"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        deleteMonthId = self.sql.query["deleteMonthId"].replace(
            "%s",
            self.sql.query["placeholder"],
        )
        cursor = self.get_cursor()
        weeks, months = set(), set()
        for wid, mid in self.wmold:
            self._clear_period_caches(cursor, wid, mid)
            weeks.add(wid)
            months.add(mid)

        self._delete_orphan_periods(cursor, weeks, selectWeekId, deleteWeekId)
        self._delete_orphan_periods(cursor, months, selectMonthId, deleteMonthId)

        for wid, mid in self.wmnew:
            self._clear_period_caches(cursor, wid, mid)

        self._rebuild_period_caches(cursor)
        self.commit()

    def rebuild_caches(self) -> None:
        tables: tuple[str, ...] | set[str]
        if self.callHud and self.cacheSessions:
            tables = ("HudCache", "CardsCache", "PositionsCache")
        elif self.callHud:
            tables = ("HudCache",)
        elif self.cacheSessions:
            tables = ("CardsCache", "PositionsCache")
        else:
            tables = set()
        for t in tables:
            self.rebuild_cache(None, None, t)

    def resetClean(self) -> None:
        self.ttold = set()
        self.ttnew = set()
        self.wmold = set()
        self.wmnew = set()

    def cleanRequired(self) -> bool:
        return bool(self.ttold or self.wmold)

    # end def createOrUpdateTourney

    # end def getTourneyPlayerInfo

    def cleanup_connections(self) -> None:
        """Clean up database connections to prevent timeouts and pool exhaustion."""
        cursor = getattr(self, "cursor", None)
        if cursor:
            with contextlib.suppress(Exception):
                cursor.close()
                log.debug("Database cursor closed.")
            self.cursor = None

        try:
            if hasattr(self, "connection") and self.connection:
                self.connection.close()
                self.connection = None
                self.__connected = False
                log.debug("Database connection closed.")
        except Exception as e:  # intentional broad catch: connection cleanup best-effort, log warning
            log.warning(f"Error closing connection: {e}")

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
