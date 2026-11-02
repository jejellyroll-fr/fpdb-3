"""Connecting to the database, transactions, and recovering a lost connection.

Split out of Database.py (#452); mixed into Database.
"""

import contextlib
import math
import os
import sys
from collections.abc import Callable
from decimal import Decimal
from importlib import import_module
from time import sleep, time
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.database_schema import DB_VERSION
from fpdb_3_legacy.db_reconnect import (
    MYSQL_NETWORK_KWARGS,
    PG_NETWORK_KWARGS,
    RECONNECT_COOLDOWN,
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

log = get_logger("database")


# Every SQLite connection runs in WAL mode. With synchronous=OFF a crash of the
# operating system or a power cut can corrupt the database file, not only lose
# the last transactions; in WAL mode NORMAL is corruption-safe and still skips
# the fsync on each commit (it syncs at checkpoints), so imports stay fast (#436).
SQLITE_SYNCHRONOUS_PRAGMA = "PRAGMA synchronous=NORMAL"

#    FreePokerTools modules


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

    def step(self, value: Any) -> None:
        self.store.append(value)

    def finalize(self) -> Any:
        return float(var(self.store))


class sqlitemath:
    def mod(self, a: Any, b: Any) -> Any:
        return a % b


def adapt_decimal(d: Any) -> Any:
    return str(d)


def convert_decimal(s: Any) -> Any:
    log.debug(f"Converting value: {s}")
    s = s.decode()
    return Decimal(s)


def _mysql_connection_kwargs(host: Any, port: Any, user: Any, password: Any, database: Any) -> dict[str, Any]:
    """What both MySQL connection paths pass to the driver.

    ``utf8mb4`` is not a preference. ``Players.name`` holds supplementary characters as
    ``utf8mb4`` since #417, and MySQL's ``utf8`` client character set is three bytes wide: with
    it, a hand naming ``Alice😀`` is refused by the server (``incorrect string value``) before
    the name reaches a column that can hold it. One helper rather than the same dict twice, so
    a character set fix cannot reach one connection path and miss the other.
    """
    kwargs: dict[str, Any] = {
        "host": host,
        "user": user,
        "passwd": password,
        "db": database,
        "charset": "utf8mb4",
        "use_unicode": True,
        **MYSQL_NETWORK_KWARGS,
    }
    if port:
        kwargs["port"] = int(port)
    return kwargs


# These are for appendStats. Insert new stats at the right place, because
# SQL needs strict order.


class DatabaseTransaction:
    """Context manager for grouping database operations into a single transaction.

    Nested context managers increment the transaction depth, and only the outermost
    context manager executes the commit or rollback.
    """

    def __init__(self, db: Any) -> None:
        self.db = db

    def __enter__(self) -> "DatabaseTransaction":
        self.db._in_transaction += 1
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
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


class DatabaseConnectionMixin:
    """Open, check, commit, roll back, close and recover the main connection.

    ``self._Database__connected`` is Database's ``self.__connected``: name mangling
    uses the class the code is written in, so it is spelled out here.
    """

    # Provided by Database.
    PGSQL: Any
    SQLITE: Any
    _Database__connected: bool
    _connection_down_logged: Any
    _in_transaction: Any
    _reconnect_blocked_until: Any
    backend: Any
    build_full_hudcache: Any
    cacheSessions: Any
    callHud: Any
    config: Any
    connection: Any
    cursor: Any
    database: Any
    date_ndays_ago: Any
    date_nhands_ago: Any
    day_start: Any
    db_path: Any
    db_server: Any
    gtcache: Any
    h_date_ndays_ago: Any
    hand_1day_ago: Any
    hand_inc: Any
    host: Any
    import_options: Any
    password: Any
    pcache: Any
    port: Any
    publicDB: Any
    saveActions: Any
    sessionTimeout: Any
    tcache: Any
    tpcache: Any
    user: Any
    wrongDbVersion: Any

    if TYPE_CHECKING:
        # Declared as callables rather than stub methods: pylint reads a stub's
        # empty body as a method that returns nothing.
        close_worker_pool: Callable[..., None]
        connect: Callable[..., None]
        ensure_feature_tables: Callable[..., None]
        get_cursor: Callable[..., Any]
        get_sites: Callable[..., None]
        recreate_tables: Callable[..., None]

    def connection_params_changed(self, c: Any) -> bool:
        """Return whether ``c`` points at a different database than the live one."""
        db_params = c.get_db_parameters()
        return bool(
            db_params["db-backend"] != self.backend
            or db_params["db-server"] != self.db_server
            or db_params["db-databaseName"] != self.database
            or db_params["db-host"] != self.host
        )

    def rebind_config(self, c: Any) -> bool:
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

    def _connect_and_configure(self, c: Any) -> None:
        """Open the connection, then set up what needs an open connection."""
        # connect to db
        self.do_connect(c)

        if self.backend == self.PGSQL:
            pass
            # ISOLATION_LEVEL_AUTOCOMMIT     = 0
            # ISOLATION_LEVEL_READ_COMMITTED = 1
            # ISOLATION_LEVEL_SERIALIZABLE   = 2

        if self.backend == self.SQLITE and self.database == ":memory:" and self.wrongDbVersion and self.is_connected():
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

    def do_connect(self, c: Any) -> None:
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
            self._Database__connected = False
            raise

        db_params = c.get_db_parameters()
        self.import_options = c.get_import_parameters()
        self.backend = db_params["db-backend"]
        self.db_server = db_params["db-server"]
        self.database = db_params["db-databaseName"]
        self.host = db_params["db-host"]
        self.port = db_params["db-port"]

    def _connect_mysql(self, host: Any, port: Any, user: Any, password: Any, database: Any) -> None:
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
            kwargs = _mysql_connection_kwargs(host, port, user, password, database)

            self.connection = MySQLdb.connect(**kwargs)
            self._Database__connected = True
        except MySQLdb.Error as ex:
            if ex.args[0] == 1045:
                raise FpdbMySQLAccessDenied(ex.args[0], ex.args[1])
            if ex.args[0] == 2002 or ex.args[0] == 2003:  # 2002 is no unix socket, 2003 is no tcp socket
                raise FpdbMySQLNoDatabase(ex.args[0], ex.args[1])
            log.exception("UNKNOWN MYSQL ERROR: {ex}")
        c = self.get_cursor()
        c.execute("show variables like 'auto_increment_increment'")
        self.hand_inc = int(c.fetchone()[1])

    def _connect_postgresql(self, host: Any, port: Any, user: Any, password: Any, database: Any) -> None:
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
        self._Database__connected = False
        if self.host in ("localhost", "127.0.0.1"):
            try:
                self.connection = psycopg.connect(dbname=database, **PG_NETWORK_KWARGS)
                self._Database__connected = True
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
                self._Database__connected = True
            except (
                Exception
            ) as ex:  # intentional broad catch: psycopg connection error inspected and re-raised as a typed FpdbError
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

    def _connect_sqlite(self, database: Any, create: Any) -> Any:
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
            self._Database__connected = True
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
                SQLITE_SYNCHRONOUS_PRAGMA,
            )  # crash-safe in WAL mode, see SQLITE_SYNCHRONOUS_PRAGMA
            self.cursor.execute(
                "PRAGMA busy_timeout=60000",
            )  # wait up to 60 seconds for locks
            self.cursor.execute(
                "PRAGMA cache_size=10000",
            )  # increase cache size for better performance
        else:
            raise FpdbError("sqlite database " + database + " does not exist")
        return database, create

    def check_version(self, database: Any, create: Any) -> None:
        self.wrongDbVersion = False
        try:
            self.cursor.execute("SELECT * FROM Settings")
            settings = self.cursor.fetchone()
            if settings[0] != DB_VERSION:
                log.error(
                    f"Outdated or too new database version ({settings[0]}). Back up the database first: "
                    "recreating tables deletes all imported hands and statistics and requires reimport.",
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
            # re-try commit if it fails in case this happened. Only a lock is worth the
            # wait: a closed or missing connection, a full disk or an I/O error fails the
            # same way every time, and each pause blocks the caller -- the Qt main thread
            # for the Session Guard (#428). Extended codes (SQLITE_BUSY_SNAPSHOT, ...)
            # carry their primary code in the low byte.
            import sqlite3

            maxtimes = 5
            pause = 1
            ok = False
            for i in range(maxtimes):
                try:
                    self.connection.commit()
                    # log.debug(("commit finished ok, i = ")+str(i))
                    ok = True
                except sqlite3.OperationalError as e:
                    primary = (getattr(e, "sqlite_errorcode", None) or 0) & 0xFF
                    if primary not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                        log.exception(f"commit {i} failed, not retried: info={sys.exc_info()}, value={e}")
                        break
                    log.exception(f"commit {i} failed: info={sys.exc_info()}, value={e}")
                    sleep(pause)
                except Exception as e:  # intentional broad catch: reported as the FpdbError below
                    log.exception(f"commit {i} failed, not retried: info={sys.exc_info()}, value={e}")
                    break
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

    def connected(self) -> bool:
        """Now deprecated, use is_connected() instead."""
        return self._Database__connected

    def is_connected(self) -> bool:
        return self._Database__connected

    def close_connection(self) -> None:
        if getattr(self, "connection", None):
            self.connection.close()
            self.connection = None
        self._Database__connected = False

    def _close_cursor_quietly(self) -> None:
        cursor = getattr(self, "cursor", None)
        if not cursor:
            return
        with contextlib.suppress(Exception):
            cursor.close()
        self.cursor = None

    def disconnect(self, due_to_error: bool=False) -> None:
        """Disconnects the DB (rolls back if param is true, otherwise commits."""
        # Guarded like close_connection and _close_cursor_quietly below: a
        # database closed once already has no connection to commit, and calling
        # disconnect twice -- which shutdown paths do -- should be a no-op
        # rather than an AttributeError on the way out.
        self.close_worker_pool()
        if self.connection is not None:
            if due_to_error:
                self.connection.rollback()
            else:
                self.connection.commit()
        self._close_cursor_quietly()
        self.close_connection()
        self._Database__connected = False

    def reconnect(self, due_to_error: bool=False) -> None:
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
        self.close_worker_pool()
        self._close_cursor_quietly()
        with contextlib.suppress(Exception):
            if self.connection is not None:
                self.connection.close()
        self.connection = None
        self._Database__connected = False

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

    def get_db_info(self) -> Any:
        return (self.host, self.database, self.user, self.password)

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
                self._Database__connected = False
                log.debug("Database connection closed.")
        except Exception as e:  # intentional broad catch: connection cleanup best-effort, log warning
            log.warning(f"Error closing connection: {e}")
