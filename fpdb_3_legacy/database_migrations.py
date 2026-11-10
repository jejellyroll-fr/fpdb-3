"""Bringing a database created by older code up to the current schema.

Split out of database_schema (#452 follow-up): these methods run on every connection
and add what an older database lacks, each one best-effort and bounded so that it can
never hang the caller. The column catalogues they apply live here too.

The ``# nosemgrep`` statements interpolate table and column names spelled in this
module or by its callers, never input.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.action_events import ACTION_EVENT_COLUMNS
from fpdb_3_legacy.database_caches import CACHE_KEYS, HUDCACHE_EXTRA_KEYS
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.sql_indexes import ANALYTICS_INDEX_NAMES

log = get_logger("db")

# How long a migration may wait for a table lock before giving up.
#
# PostgreSQL and MySQL both wait forever by default, and ``ensure_feature_tables``
# runs from Database() construction -- which the GUI does once per heavy
# tab. One tab left idle inside a read transaction on Gametypes is enough to
# make the next tab's ALTER TABLE wait on it for the life of the process, on the
# GUI thread, with no timeout and nothing logged: the freeze reported in #249.
# Migrations are re-attempted (see FEATURE_TABLES_RECHECK_S), so losing a race is
# a delay until the next attempt, while blocking on it is the application hanging.
DDL_LOCK_TIMEOUT_MS = 2000

# How long a process trusts the last migration pass on a server database. The
# pass is about 50 statements: at 10 ms a round trip, every new connection cost
# seconds before it could do any work (#680). It stays periodic rather than
# once per process because each migration is best-effort, and one that lost a
# race for a lock must get another chance.
FEATURE_TABLES_RECHECK_S = 600.0
_feature_tables_checked: dict[tuple[Any, ...], float] = {}
_feature_tables_lock = threading.Lock()

# Width Gametypes.category must have for aof_holdem (10 chars) to fit. The
# statements are spelled out rather than formatted from the constant: the
# quality gate rejects SQL built by string interpolation, whatever the input.
GAMETYPE_CATEGORY_WIDTH = 10
WIDEN_GAMETYPE_CATEGORY_MYSQL = "ALTER TABLE Gametypes MODIFY category VARCHAR(10) NOT NULL"
WIDEN_GAMETYPE_CATEGORY_SQL = "ALTER TABLE Gametypes ALTER COLUMN category TYPE VARCHAR(10)"

# Reads a column's declared width. MySQL needs the schema pinned because
# information_schema.columns spans every database on the server; PostgreSQL's
# is already scoped to the connected one.
# Sites registered after databases already existed. fillDefaultData only runs
# when the tables are created, so an older database lacks these rows, and its
# hands would break the Sites foreign key once a parser files them there.
SITES_ADDED_LATER: tuple[tuple[int, str, str], ...] = (
    (132, "Bet365.fr Poker", "IP"),
    (142, "Betclic", "BC"),  # #730: the 2025+ in-house client
)
INSERT_SITE_QMARK = "INSERT INTO Sites (id,name,code) VALUES (?,?,?)"
INSERT_SITE_FORMAT = "INSERT INTO Sites (id,name,code) VALUES (%s,%s,%s)"

COLUMN_WIDTH_SQL = (
    "SELECT character_maximum_length FROM information_schema.columns "
    "WHERE lower(table_name) = %s AND lower(column_name) = %s"
)
COLUMN_WIDTH_MYSQL = (
    "SELECT character_maximum_length FROM information_schema.columns "
    "WHERE lower(table_name) = %s AND lower(column_name) = %s AND table_schema = DATABASE()"
)

# Reads a column's collation, for the one migration that has to know it before issuing DDL.
# Scoped to the current database on MySQL for the reason COLUMN_WIDTH_MYSQL is. PostgreSQL's
# catalogue is scoped to the connected database but not to one schema, so the schema is
# resolved from the table name exactly as the unqualified ALTER TABLE resolves it: a database
# that holds a Players table in more than one schema must not answer for another one's row,
# or the migration would skip the table it is about to alter -- or alter it every connection.
COLUMN_COLLATION_SQL = (
    "SELECT collation_name FROM information_schema.columns "
    "WHERE lower(table_name) = %s AND lower(column_name) = %s AND table_schema = ("
    "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE c.oid = to_regclass(%s))"
)
COLUMN_COLLATION_MYSQL = (
    "SELECT collation_name FROM information_schema.columns "
    "WHERE lower(table_name) = %s AND lower(column_name) = %s AND table_schema = DATABASE()"
)

# Players.name compares byte for byte after this migration (#417): case, accents and ligatures
# are distinct, so the unique (name, siteId) index no longer files two players as one. The
# character set is named with the collation because a collation belongs to one character set;
# MySQL's utf8mb4_bin is PAD SPACE, so a trailing space still compares equal there.
SET_PLAYERS_NAME_COLLATION_MYSQL = (
    "ALTER TABLE Players MODIFY name VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL"
)
SET_PLAYERS_NAME_COLLATION_PGSQL = 'ALTER TABLE Players ALTER COLUMN name TYPE VARCHAR(32) COLLATE "C"'

# PostgreSQL's collations that compare a name byte for byte. Anything else -- its locale, or
# MySQL's server default -- folds at least case, or is not known not to.
PGSQL_BINARY_COLLATIONS = frozenset({"c", "posix", "ucs_basic"})


def _is_binary_collation(collation: str | None, *, mysql: bool) -> bool:
    """Whether *collation* stores and compares a name as the migration leaves it.

    ``None`` is the server's default, and a default is never taken for binary: MySQL's usual
    one folds case and accents, and PostgreSQL's is its locale, which is not known to do
    otherwise. On MySQL a binary collation counts only in ``utf8mb4`` (``utf8mb4_bin``,
    ``utf8mb4_0900_bin``): ``latin1_bin`` or ``utf8mb3_bin`` compare byte for byte but cannot
    store every name -- ``Alice😀`` is refused at insertion -- so they are migrated too.
    """
    if collation is None:
        return False
    normalised = collation.lower()
    if mysql:
        return normalised.startswith("utf8mb4_") and normalised.endswith("_bin")
    return normalised in PGSQL_BINARY_COLLATIONS


# Session settings that apply DDL_LOCK_TIMEOUT_MS on each server backend.
SET_PGSQL_LOCK_TIMEOUT = "SET lock_timeout = 2000"
RESET_PGSQL_LOCK_TIMEOUT = "SET lock_timeout = DEFAULT"
SET_MYSQL_LOCK_TIMEOUT = "SET SESSION lock_wait_timeout = 2"
RESET_MYSQL_LOCK_TIMEOUT = "SET SESSION lock_wait_timeout = DEFAULT"

# Keys used to index into player data in storeHandsPlayers.
HANDS_PLAYERS_KEYS = [
    "startCash",
    "effStack",
    "startBounty",
    "endBounty",
    "seatNo",
    "sitout",
    "card1",
    "card2",
    "card3",
    "card4",
    "card5",
    "card6",
    "card7",
    "card8",
    "card9",
    "card10",
    "card11",
    "card12",
    "card13",
    "card14",
    "card15",
    "card16",
    "card17",
    "card18",
    "card19",
    "card20",
    "common",
    "committed",
    "winnings",
    "rake",
    "rakeDealt",
    "rakeContributed",
    "rakeWeighted",
    "totalProfit",
    "allInEV",
    "allInEVCalculated",
    "street0VPIChance",
    "street0VPI",
    "street1Seen",
    "street2Seen",
    "street3Seen",
    "street4Seen",
    "sawShowdown",
    "showed",
    "street0AllIn",
    "street1AllIn",
    "street2AllIn",
    "street3AllIn",
    "street4AllIn",
    "wentAllIn",
    "splashWinnings",
    "street0AggrChance",
    "street0Aggr",
    "street1Aggr",
    "street2Aggr",
    "street3Aggr",
    "street4Aggr",
    "street1CBChance",
    "street2CBChance",
    "street3CBChance",
    "street4CBChance",
    "street1CBDone",
    "street2CBDone",
    "street3CBDone",
    "street4CBDone",
    "wonWhenSeenStreet1",
    "wonWhenSeenStreet2",
    "wonWhenSeenStreet3",
    "wonWhenSeenStreet4",
    "wonAtSD",
    "position",
    "street0InPosition",
    "street1InPosition",
    "street2InPosition",
    "street3InPosition",
    "street4InPosition",
    "street0FirstToAct",
    "street1FirstToAct",
    "street2FirstToAct",
    "street3FirstToAct",
    "street4FirstToAct",
    "tourneysPlayersId",
    "startCards",
    "street0CalledRaiseChance",
    "street0CalledRaiseDone",
    "street0FaceRaise",
    "street0_2BChance",
    "street0_2BDone",
    "street0_3BChance",
    "street0_3BDone",
    "street0_4BChance",
    "street0_4BDone",
    "street0_C4BChance",
    "street0_C4BDone",
    "street0_FoldTo2BChance",
    "street0_FoldTo2BDone",
    "street0_FoldTo3BChance",
    "street0_FoldTo3BDone",
    "street0_FoldTo4BChance",
    "street0_FoldTo4BDone",
    "street0_SqueezeChance",
    "street0_SqueezeDone",
    "raiseToStealChance",
    "raiseToStealDone",
    "stealChance",
    "stealDone",
    "success_Steal",
    "otherRaisedStreet0",
    "otherRaisedStreet1",
    "otherRaisedStreet2",
    "otherRaisedStreet3",
    "otherRaisedStreet4",
    "foldToOtherRaisedStreet0",
    "foldToOtherRaisedStreet1",
    "foldToOtherRaisedStreet2",
    "foldToOtherRaisedStreet3",
    "foldToOtherRaisedStreet4",
    "raiseFirstInChance",
    "raisedFirstIn",
    "foldBbToStealChance",
    "foldedBbToSteal",
    "foldSbToStealChance",
    "foldedSbToSteal",
    "foldToStreet1CBChance",
    "foldToStreet1CBDone",
    "foldToStreet2CBChance",
    "foldToStreet2CBDone",
    "foldToStreet3CBChance",
    "foldToStreet3CBDone",
    "foldToStreet4CBChance",
    "foldToStreet4CBDone",
    "street1CheckCallRaiseChance",
    "street1CheckCallDone",
    "street1CheckRaiseDone",
    "street2CheckCallRaiseChance",
    "street2CheckCallDone",
    "street2CheckRaiseDone",
    "street3CheckCallRaiseChance",
    "street3CheckCallDone",
    "street3CheckRaiseDone",
    "street4CheckCallRaiseChance",
    "street4CheckCallDone",
    "street4CheckRaiseDone",
    "street0Calls",
    "street1Calls",
    "street2Calls",
    "street3Calls",
    "street4Calls",
    "street0Bets",
    "street1Bets",
    "street2Bets",
    "street3Bets",
    "street4Bets",
    "street0Raises",
    "street1Raises",
    "street2Raises",
    "street3Raises",
    "street4Raises",
    "street1Discards",
    "street2Discards",
    "street3Discards",
    "street0Limp",
    "street0OpenLimp",
    "handString",
    "cashOutFee",
    "isCashOut",
    # Postflop per-street 3-bet (re-raise) — appended at the end so existing
    # insert column positions are unchanged (see store_hands_players).
    "street1_3BChance",
    "street1_3BDone",
    "street2_3BChance",
    "street2_3BDone",
    "street3_3BChance",
    "street3_3BDone",
    "street1_4BChance",
    "street1_4BDone",
    "street1_FoldTo4BChance",
    "street1_FoldTo4BDone",
    "street2_4BChance",
    "street2_4BDone",
    "street2_FoldTo4BChance",
    "street2_FoldTo4BDone",
    "street3_4BChance",
    "street3_4BDone",
    "street3_FoldTo4BChance",
    "street3_FoldTo4BDone",
    "street1OpenChance",
    "street1OpenDone",
    "street2OpenChance",
    "street2OpenDone",
    "street3OpenChance",
    "street3OpenDone",
    "flg_f_fold",
    "flg_t_fold",
    "flg_r_fold",
    "street1FirstRaise",
    "street2FirstRaise",
    "street3FirstRaise",
    "street1FaceRaise",
    "street2FaceRaise",
    "street3FaceRaise",
    "flg_f_donk_def_opp",
    "flg_t_float_opp",
    "flg_t_float",
    "flg_t_float_def_opp",
    "flg_r_float_opp",
    "flg_r_float",
    "flg_r_float_def_opp",
    "flg_t_donk_def_opp",
    "flg_r_donk_def_opp",
    # Fold-to-3bet postflop (computed in calc3BetPostflop) — appended at the end.
    "street1_FoldTo3BChance",
    "street1_FoldTo3BDone",
    "street2_FoldTo3BChance",
    "street2_FoldTo3BDone",
    "street3_FoldTo3BChance",
    "street3_FoldTo3BDone",
    # Preflop squeeze defense + limpers faced — appended at the end.
    "street0_FoldToSqueezeChance",
    "street0_FoldToSqueezeDone",
    "street0_FaceLimpers",
    # GenerationPoker open-sizing / limp counts (PT4 cnt_gp_* custom pack).
    "cnt_gp_open_opp",
    "cnt_gp_2x",
    "cnt_gp_os",
    "cnt_gp_limp",
    # Special blinds (dead small/big blind, straddle) — appended at the end.
    "flg_blind_ds",
    "flg_blind_db",
    "flg_blind_k",
    # Faced an all-in + fold response — appended at the end.
    "flg_faced_allin",
    "flg_fold_to_allin",
    # Bet-sizing: flop bet faced (count + basis points of pot) — appended at the end.
    "cnt_f_bet_facing",
    "val_f_bet_facing_bp",
    # Bet-sizing: turn + river bet faced — appended at the end.
    "cnt_t_bet_facing",
    "val_t_bet_facing_bp",
    "cnt_r_bet_facing",
    "val_r_bet_facing_bp",
    # Bet-sizing: preflop raise faced per level (count + basis points) — appended at the end.
    "cnt_p_2bet_facing",
    "val_p_2bet_facing_bp",
    "cnt_p_3bet_facing",
    "val_p_3bet_facing_bp",
    "cnt_p_4bet_facing",
    "val_p_4bet_facing_bp",
    # Bet-sizing: postflop bet made per street (count + basis points) — appended at the end.
    "cnt_f_bet_made",
    "val_f_bet_made_bp",
    "cnt_t_bet_made",
    "val_t_bet_made_bp",
    "cnt_r_bet_made",
    "val_r_bet_made_bp",
    # Bet-sizing: postflop SPR per street (count + SPR*100) — appended at the end.
    "cnt_f_spr",
    "val_f_spr",
    "cnt_t_spr",
    "val_t_spr",
    "cnt_r_spr",
    "val_r_spr",
    # Bet-sizing: size of the first raise made per street (count + basis points) — appended at the end.
    "cnt_p_raise_made",
    "val_p_raise_made_bp",
    "cnt_f_raise_made",
    "val_f_raise_made_bp",
    "cnt_t_raise_made",
    "val_t_raise_made_bp",
    "cnt_r_raise_made",
    "val_r_raise_made_bp",
    # Bet-sizing: postflop raise faced per street and level (count + basis points) — appended at the end.
    "cnt_f_2bet_facing",
    "val_f_2bet_facing_bp",
    "cnt_f_3bet_facing",
    "val_f_3bet_facing_bp",
    "cnt_f_4bet_facing",
    "val_f_4bet_facing_bp",
    "cnt_t_2bet_facing",
    "val_t_2bet_facing_bp",
    "cnt_t_3bet_facing",
    "val_t_3bet_facing_bp",
    "cnt_t_4bet_facing",
    "val_t_4bet_facing_bp",
    "cnt_r_2bet_facing",
    "val_r_2bet_facing_bp",
    "cnt_r_3bet_facing",
    "val_r_3bet_facing_bp",
    "cnt_r_4bet_facing",
    "val_r_4bet_facing_bp",
    # Bet-sizing completion (raw amounts, generic raise faced, 2nd raise, 5bet) — appended at the end.
    "amt_blind",
    "amt_bet_p",
    "amt_bet_f",
    "amt_bet_t",
    "amt_bet_r",
    "amt_bet_ttl",
    "cnt_p_raise_facing",
    "val_p_raise_facing_bp",
    "cnt_f_raise_facing",
    "val_f_raise_facing_bp",
    "cnt_t_raise_facing",
    "val_t_raise_facing_bp",
    "cnt_r_raise_facing",
    "val_r_raise_facing_bp",
    "cnt_p_raise_made_2",
    "val_p_raise_made_2_bp",
    "cnt_f_raise_made_2",
    "val_f_raise_made_2_bp",
    "cnt_t_raise_made_2",
    "val_t_raise_made_2_bp",
    "cnt_r_raise_made_2",
    "val_r_raise_made_2_bp",
    "cnt_p_5bet_facing",
    "val_p_5bet_facing_bp",
    # Delayed turn c-bet (DerivedStats._calc_delayed_turn_cbet). Appended at the
    # end so existing insert column positions stay unchanged; older databases get
    # the columns via ensure_handsplayers_columns().
    "street2DelayedCBChance",
    "street2DelayedCBDone",
    # Turn probe bet (DerivedStats._calc_turn_probe).
    "street2ProbeChance",
    "street2ProbeDone",
    # PT4 action enums (DerivedStats.calcActionEnums). One char per column --
    # F/C/R for the response, N when the situation never came up -- so they are
    # CHAR(1) rather than the INT the other stat columns use. The order mirrors
    # DerivedStats.ACTION_ENUM_KEYS and the store_hands_players insert.
    "enum_p_3bet_action",
    "enum_p_4bet_action",
    "enum_p_squeeze_action",
    "enum_f_3bet_action",
    "enum_f_4bet_action",
    "enum_f_cbet_action",
    "enum_f_donk_action",
    "enum_t_3bet_action",
    "enum_t_4bet_action",
    "enum_t_cbet_action",
    "enum_t_float_action",
    "enum_t_donk_action",
    "enum_r_3bet_action",
    "enum_r_4bet_action",
    "enum_r_cbet_action",
    "enum_r_float_action",
    "enum_r_donk_action",
    "enum_face_allin",
    "enum_face_allin_action",
    "enum_folded",
]

# The subset of HANDS_PLAYERS_KEYS holding a PT4 action enum. Split out so the
# migration can give them a char column instead of the INT default.
ACTION_ENUM_COLUMNS = [key for key in HANDS_PLAYERS_KEYS if key.startswith("enum_")]

# Just like STATS_KEYS, this lets us efficiently add data at the
# "beginning" later.
HANDS_PLAYERS_KEYS.reverse()

# Column definition per normalized action-event column (issue #293). The
# mapping is keyed by every column action_events.ACTION_EVENT_COLUMNS declares,
# and spelled out so that adding a column without deciding how an existing
# database gains it fails here, at import, rather than in the ALTER of whoever
# upgrades next.
_HANDS_ACTIONS_EVENT_TYPES = {
    "actionType": "VARCHAR(24)",
    "toCall": "BIGINT DEFAULT 0",
    "potBefore": "BIGINT DEFAULT 0",
    "potAfter": "BIGINT DEFAULT 0",
    "sizingBp": "INT DEFAULT 0",
    "position": "SMALLINT",
    "relativePosition": "SMALLINT DEFAULT 0",
    "inPosition": "BOOLEAN DEFAULT false",
    "effectiveStack": "BIGINT DEFAULT 0",
    "effectiveStackBB": "INT DEFAULT 0",
    "sprBefore": "INT DEFAULT 0",
    "isAggressor": "BOOLEAN DEFAULT false",
    "facingActionType": "VARCHAR(24)",
    "facingAmount": "BIGINT DEFAULT 0",
    "facingSizingBp": "INT DEFAULT 0",
    "raiserCount": "SMALLINT DEFAULT 0",
    "callerCount": "SMALLINT DEFAULT 0",
    "playersInHand": "SMALLINT DEFAULT 0",
}
HANDS_ACTIONS_EVENT_DEFINITIONS: dict[str, str] = {
    column: _HANDS_ACTIONS_EVENT_TYPES[column] for column in ACTION_EVENT_COLUMNS
}


class DatabaseMigrationsMixin:
    """Upgrades an existing database in place.

    Mixed into Database through DatabaseSchemaMixin.
    """

    # Provided by Database.
    sql: Any
    backend: int
    host: Any
    port: Any
    database: Any
    MYSQL_INNODB: int
    PGSQL: int
    SQLITE: int

    if TYPE_CHECKING:
        # Declared as callables rather than stub methods: pylint reads a stub's
        # empty body as a method that returns nothing.
        commit: Callable[..., None]
        get_cursor: Callable[..., Any]
        rollback: Callable[..., None]

    @contextlib.contextmanager
    def bounded_ddl_lock_wait(self) -> Iterator[None]:
        """Make every migration inside the block fail rather than block.

        A migration that cannot take its lock is a migration that has to wait
        for another connection to end its transaction -- something a GUI tab
        holding an open read can keep doing for hours. Both server backends
        wait for that lock forever unless told otherwise, so the statement
        never raises, never logs, and never returns: the caller simply stops.

        The timeout is set on the session rather than with SET LOCAL because
        the block below commits between statements, and a SET LOCAL would not
        survive the commit. It is restored on the way out, so nothing outside
        this block inherits it. SQLite has no such knob (it serialises with its
        own busy timeout) and is left alone.
        """
        applied = False
        try:
            if self.backend == self.PGSQL:
                self.get_cursor().execute(SET_PGSQL_LOCK_TIMEOUT)
                applied = True
            elif self.backend == self.MYSQL_INNODB:
                # MySQL counts metadata-lock waits in whole seconds, minimum 1.
                self.get_cursor().execute(SET_MYSQL_LOCK_TIMEOUT)
                applied = True
        except Exception:  # noqa: BLE001 - an unsupported knob must not stop the migrations
            log.debug("Could not bound the migration lock wait", exc_info=True)
        try:
            yield
        finally:
            if applied:
                # The last statement may have left the connection in an aborted
                # transaction, which refuses everything until it is rolled back.
                with contextlib.suppress(Exception):
                    self.rollback()
                with contextlib.suppress(Exception):
                    if self.backend == self.PGSQL:
                        self.get_cursor().execute(RESET_PGSQL_LOCK_TIMEOUT)
                    else:
                        self.get_cursor().execute(RESET_MYSQL_LOCK_TIMEOUT)
                    self.commit()

    def ensure_feature_tables_on_connect(self) -> None:
        """Run the migration pass for a new connection, unless it just ran.

        SQLite always runs it: the file is local, so the pass costs next to
        nothing, and a path can hold a different database from one moment to the next.
        """
        if self.backend != self.SQLITE:
            key = (self.backend, self.host, self.port, self.database)
            now = time.monotonic()
            with _feature_tables_lock:
                last = _feature_tables_checked.get(key)
                if last is not None and now - last < FEATURE_TABLES_RECHECK_S:
                    return
                _feature_tables_checked[key] = now
        self.ensure_feature_tables()

    def forget_feature_tables_check(self) -> None:
        """The tables just changed: the next connection must run the pass again."""
        with _feature_tables_lock:
            _feature_tables_checked.clear()

    def ensure_feature_tables(self) -> None:
        """Create tables added after the original schema if they are missing, so
        that databases created by older versions keep working (used for the
        showdown combinations, cashout details, and additive HudCache stats).

        Runs for new connections, so it must never block: see
        :meth:`bounded_ddl_lock_wait`.
        """
        with self.bounded_ddl_lock_wait():
            self._run_feature_migrations()

    def _run_feature_migrations(self) -> None:
        """The migrations themselves, each one best-effort and self-contained."""
        for query_name in (
            "createHandsShowdownTable",
            "createHandsCashoutTable",
            "createBoardFeaturesTable",
            "createPlayerAutoNotesTable",
            "createAofDecisionsTable",
            "createAofDecisionAnalysesTable",
            "createHandsSituationsTable",
            "createHandStatesTable",
            "createTourneyPayoutsTable",
            "createActionBubbleFactorsTable",
        ):
            try:
                c = self.get_cursor()
                c.execute(self.sql.query[query_name])
                self.commit()
            except Exception:  # noqa: BLE001 - table already exists: nothing to do.
                self.rollback()

        for query_name in (
            "addBoardFeaturesHandIndex",
            "addBoardFeaturesTextureIndex",
            "addPlayerAutoNotesPlayerIndex",
            "addPlayerAutoNotesHandIndex",
            "addPlayerAutoNotesRuleIndex",
            "addAofDecisionsPlayerIndex",
            "addAofDecisionsHandIndex",
            "addAofDecisionsRangeIndex",
            "addAofAnalysesDecisionIndex",
            "addAofAnalysesStatusIndex",
            "addActionBubbleFactorsTourneyIndex",
            # The analytics fact-table indexes (#304). Best-effort like the
            # rest: a database that already has them rolls back and moves on.
            *ANALYTICS_INDEX_NAMES,
        ):
            try:
                c = self.get_cursor()
                c.execute(self.sql.query[query_name])
                self.commit()
            except Exception:  # noqa: BLE001 - index/table already exists or feature table absent.
                self.rollback()

        self._ensure_gametype_category_width()
        self._ensure_players_name_collation()
        self.ensure_sites_rows()

        # The analytics lifecycle bookkeeping (#305): the meta table itself,
        # then the version stamps. On a database that predates versioning the
        # subsystems stay unrecorded (stale by definition) until a rebuild
        # claims them -- only a fresh recreate_tables gets born current.
        from fpdb_3_legacy import analytics_lifecycle

        analytics_lifecycle.ensure_analytics_meta(self)

        self.ensure_hudcache_columns()
        self.ensure_handsplayers_columns()
        self.ensure_hands_columns()
        self.ensure_tourneysplayers_columns()
        self.ensure_handsactions_columns()

    def ensure_sites_rows(self) -> None:
        """Add the Sites rows registered after this database was created."""
        try:
            c = self.get_cursor()
            c.execute("SELECT id FROM Sites")
            present = {int(row[0]) for row in c.fetchall()}
            # An empty table is about to be filled by fillDefaultData, which
            # inserts these rows itself and would collide with ours.
            missing = [row for row in SITES_ADDED_LATER if present and row[0] not in present]
            if not missing:
                return
            # A constant statement per paramstyle: SQLite takes "?", the servers "%s".
            uses_qmark = self.sql.query.get("placeholder") == "?"
            insert = INSERT_SITE_QMARK if uses_qmark else INSERT_SITE_FORMAT
            for site_id, name, code in missing:
                c.execute(insert, (site_id, name, code))
                log.info("Registered site %s as id %s", name, site_id)
            self.commit()
        except Exception:  # noqa: BLE001 - best-effort like the other migrations.
            log.warning("Could not add the missing Sites rows", exc_info=True)
            self.rollback()

    def _get_table_columns(self, table: str) -> set[str]:
        c = self.get_cursor()
        if self.backend == self.SQLITE:
            c.execute(f"PRAGMA table_info({table})")  # nosemgrep
            return {row[1] for row in c.fetchall()}
        if self.backend == self.MYSQL_INNODB:
            c.execute(f"SHOW COLUMNS FROM {table}")  # nosemgrep
            return {row[0] for row in c.fetchall()}

        c.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s OR table_name = %s",
            (table, table.lower()),
        )
        return {row[0] for row in c.fetchall()}

    def ensure_hudcache_columns(self) -> None:
        """Add missing additive HudCache stat columns for databases created by older code."""
        definitions = {column: "INT DEFAULT 0" for column in CACHE_KEYS}
        # HudCache-only columns (not in the shared CACHE_KEYS).
        definitions.update({column: "INT DEFAULT 0" for column in HUDCACHE_EXTRA_KEYS})
        self._ensure_table_columns("HudCache", definitions)

    def ensure_handsplayers_columns(self) -> None:
        """Add missing HandsPlayers stat columns for databases created by older code."""
        definitions = {column: "INT DEFAULT 0" for column in HANDS_PLAYERS_KEYS}
        # The PT4 action enums store a single response char, not a counter.
        definitions.update({column: "CHAR(1) DEFAULT 'N'" for column in ACTION_ENUM_COLUMNS})
        definitions["handString"] = "TEXT"
        definitions["cashOutFee"] = "INT DEFAULT 0"
        definitions["isCashOut"] = "BOOLEAN DEFAULT 0"
        self._ensure_table_columns("HandsPlayers", definitions)

    def ensure_hands_columns(self) -> None:
        """Add missing additive Hands columns for databases created by older code."""
        definitions = {
            "bombPot": "INT DEFAULT 0",
            "splashPot": "INT DEFAULT 0",
        }
        self._ensure_table_columns("Hands", definitions)

    def ensure_tourneysplayers_columns(self) -> None:
        """Add the bounty money column (#447) to TourneysPlayers of databases created by older code."""
        self._ensure_table_columns("TourneysPlayers", {"koWinnings": "BIGINT"})

    def ensure_handsactions_columns(self) -> None:
        """Add missing normalized action-event columns for databases created by older code.

        The event columns (#293) are additive like the stat columns: an existing
        database gains them empty on its next connection, and the rows already
        imported keep zeros there until they are rebuilt. Docs:
        docs/action-event-model.md.
        """
        self._ensure_table_columns("HandsActions", HANDS_ACTIONS_EVENT_DEFINITIONS)

    def _column_character_length(self, table: str, column: str) -> int | None:
        """Declared width of a character column, or None when there is none.

        None covers both "no such column" and a type with no declared width, so
        callers can treat it as "nothing to widen".
        """
        c = self.get_cursor()
        # Two whole statements rather than one built by appending the MySQL
        # clause: the analyser reads any query assembled from parts as an
        # injection site, and it is right to, even when every part is a literal.
        query = COLUMN_WIDTH_MYSQL if self.backend == self.MYSQL_INNODB else COLUMN_WIDTH_SQL
        c.execute(query, (table.lower(), column.lower()))
        row = c.fetchone()
        return None if row is None else row[0]

    def _ensure_gametype_category_width(self) -> None:
        """Widen Gametypes.category to varchar(10) for aof_holdem support.

        The original schema used varchar(9), which fits aof_omaha (8 chars)
        but not aof_holdem (10 chars). Avoided on SQLite (TEXT is unbounded)
        and skipped when the column is already wide enough.

        That last sentence used to be a claim rather than a check: the only
        test was that a column named "category" exists, so an ALTER TABLE went
        out on every single connection, for the life of the schema, to set a
        width that was already set. It takes ACCESS EXCLUSIVE on Gametypes,
        which is why a database that had nothing to migrate could still hang
        the GUI behind another tab's open read (#249). Reading the width first
        makes the statement run once, on the one database that needs it.
        """
        if self.backend == self.SQLITE:
            return
        try:
            width = self._column_character_length("Gametypes", "category")
        except Exception:  # noqa: BLE001 - table absent during first-time setup
            self.rollback()
            return
        if width is None or width >= GAMETYPE_CATEGORY_WIDTH:
            return
        try:
            c = self.get_cursor()
            if self.backend == self.MYSQL_INNODB:
                c.execute(WIDEN_GAMETYPE_CATEGORY_MYSQL)
            else:
                c.execute(WIDEN_GAMETYPE_CATEGORY_SQL)
            self.commit()
            log.info("Widened Gametypes.category to varchar(%d)", GAMETYPE_CATEGORY_WIDTH)
        except Exception:  # noqa: BLE001 - another connection holds the table; retried next connection.
            self.rollback()
            log.warning(
                "Could not widen Gametypes.category to varchar(%d); retrying on the next connection",
                GAMETYPE_CATEGORY_WIDTH,
            )

    def _column_collation(self, table: str, column: str) -> str | None:
        """Declared collation of a character column, or None when it takes the default."""
        c = self.get_cursor()
        if self.backend == self.MYSQL_INNODB:
            c.execute(COLUMN_COLLATION_MYSQL, (table.lower(), column.lower()))
        else:
            # The table name goes to ``to_regclass`` as written, so the catalogue row is the
            # one the unqualified ``ALTER TABLE`` addresses.
            c.execute(COLUMN_COLLATION_SQL, (table.lower(), column.lower(), table))
        row = c.fetchone()
        return None if row is None else row[0]

    def players_name_compares_binary(self) -> bool:
        """Whether ``Players.name`` compares names byte for byte on this connection (#417).

        :meth:`_ensure_players_name_collation` is best-effort, like every migration that runs
        from :meth:`ensure_feature_tables`: a table lock it cannot take is logged and retried on
        the next connection. The DDL it issues therefore cannot be assumed to have run, and a
        caller that stores two names differing only in case relies on it: under the server's
        default collation the unique ``(name, siteId)`` index files them as one row, and
        ``insertPlayer()`` hands the second name the first player's id, merging their actions
        and results for good. Asking the catalogue here, immediately before such an import,
        turns that silent merge into a refused import the next connection can retry.

        SQLite's default comparison is already ``BINARY``, and its DDL spells that out.
        """
        if self.backend == self.SQLITE:
            return True
        try:
            return _is_binary_collation(
                self._column_collation("Players", "name"), mysql=self.backend == self.MYSQL_INNODB
            )
        except Exception:  # noqa: BLE001 - a catalogue that cannot be read cannot vouch for the column
            self.rollback()
            return False

    def _ensure_players_name_collation(self) -> None:
        """Give ``Players.name`` an explicit binary collation (#417).

        The column was created with no ``COLLATE``, so it compared names with the server's
        default: on MySQL that ignores case and accents, and the unique index on
        ``(name, siteId)`` made ``Alice`` and ``alice`` one row -- ``insertPlayer()``'s upsert
        handed the second seat the first player's id, merging their actions and results for
        good. The column now compares byte for byte, so two such names are two players.

        Read before writing, like the Gametypes width migration: the ALTER rewrites the table
        and rebuilds the index, so it must run once, not on every connection. PostgreSQL's
        ``"C"`` makes the comparison independent of the database's locale; SQLite's default
        is already ``BINARY``.

        Reversing the migration is a statement, not a data repair: the DDL without its
        ``COLLATE`` clause restores the server default, and no row is rewritten by reverting.
        A database where the merge has *already* happened is not split -- the surviving row
        kept whichever spelling was inserted first, and the other is not recorded anywhere --
        so the log says so on the one connection that migrates.

        Losing the race for the table leaves the column folded, so callers that store two
        names which differ only in case must ask :meth:`players_name_compares_binary` rather
        than take this method's success for granted.
        """
        if self.backend == self.SQLITE:
            return
        try:
            collation = self._column_collation("Players", "name")
        except Exception:  # noqa: BLE001 - table absent during first-time setup
            self.rollback()
            return
        if _is_binary_collation(collation, mysql=self.backend == self.MYSQL_INNODB):
            return
        try:
            c = self.get_cursor()
            c.execute(
                SET_PLAYERS_NAME_COLLATION_MYSQL
                if self.backend == self.MYSQL_INNODB
                else SET_PLAYERS_NAME_COLLATION_PGSQL
            )
            self.commit()
        except Exception:  # noqa: BLE001 - another connection holds the table; retried next connection.
            self.rollback()
            log.warning(
                "Could not give Players.name a binary collation; retrying on the next connection",
                exc_info=True,
            )
            return
        log.info("Gave Players.name a binary collation: names now compare byte for byte")
        log.warning(
            "Players already merged under the old collation stay one row: the row kept only the "
            "first spelling, so the other cannot be recovered or split",
        )

    def _ensure_table_columns(self, table: str, definitions: dict[str, str]) -> None:
        try:
            existing = self._get_table_columns(table)
        except Exception:  # noqa: BLE001 - the table may not exist yet during first-time setup.
            self.rollback()
            return

        if not existing:
            return

        existing_lower = {column.lower() for column in existing}
        missing = [column for column in definitions if column.lower() not in existing_lower]
        if not missing:
            return

        c = self.get_cursor()
        try:
            for column in missing:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definitions[column]}")  # nosemgrep
            self.commit()
            log.info("Added %s missing %s columns: %s", len(missing), table, ", ".join(missing))
        except Exception:  # noqa: BLE001 - reported, then retried on the next connection
            self.rollback()
            # Raising here used to abort whatever was opening the connection.
            # Now that the block bounds its lock wait, the likeliest failure is
            # losing a race for the table -- against the HUD process starting at
            # the same time, say -- and taking down the window that lost is a
            # worse answer than saying so and trying again next connection.
            log.warning(
                "Could not add missing %s columns (%s); retrying on the next connection",
                table,
                ", ".join(missing),
                exc_info=True,
            )
