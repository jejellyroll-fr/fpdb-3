"""Index and foreign-key catalogues, and the DDL that applies them.

Split out of database_schema (#452 follow-up). The catalogues list what each backend
carries besides its primary keys; the bulk import reads them too, to drop and recreate
what would slow it down.

The ``# nosemgrep`` statements interpolate names from these catalogues, or from
information_schema in drop_referential_integrity, never input.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db")

# db differences:
# - note that mysql automatically creates indexes on constrained columns when
#   foreign keys are created, while postgres does not. Hence the much longer list
#   of indexes is required for postgres.
# all primary keys are left on all the time
#
#             table     column           drop_code

INDEXES: list[list[dict[str, Any]]] = [
    [],  # no db with index 0
    [],  # no db with index 1
    [  # indexes for mysql (list index 2) (foreign keys not here, in next data structure)
        #  {'tab':'Players',         'col':'name',              'drop':0}  unique indexes not dropped
        #  {'tab':'Hands',           'col':'siteHandNo',        'drop':0}  unique indexes not dropped
        # , {'tab':'Tourneys',        'col':'siteTourneyNo',     'drop':0}  unique indexes not dropped
    ],
    [  # indexes for postgres (list index 3)
        {"tab": "Gametypes", "col": "siteId", "drop": 0},
        {"tab": "Hands", "col": "tourneyId", "drop": 0},  # mct 22/3/09
        {"tab": "Hands", "col": "gametypeId", "drop": 0},  # mct 22/3/09
        {"tab": "Hands", "col": "sessionId", "drop": 0},  # mct 22/3/09
        {"tab": "Hands", "col": "fileId", "drop": 0},  # mct 22/3/09
        # , {'tab':'Hands',           'col':'siteHandNo',        'drop':0}  unique indexes not dropped
        {"tab": "HandsActions", "col": "handId", "drop": 1},
        {"tab": "HandsActions", "col": "playerId", "drop": 1},
        {"tab": "HandsActions", "col": "actionId", "drop": 1},
        # The event model is queried street by street and by action type
        # (#293), which the two foreign-key indexes above cannot serve.
        {"tab": "HandsActions", "col": "street", "drop": 1},
        {"tab": "HandsActions", "col": "actionType", "drop": 1},
        {"tab": "HandsStove", "col": "handId", "drop": 1},
        {"tab": "HandsStove", "col": "playerId", "drop": 1},
        {"tab": "HandsStove", "col": "hiLo", "drop": 1},
        {"tab": "HandsPots", "col": "handId", "drop": 1},
        {"tab": "HandsPots", "col": "playerId", "drop": 1},
        {"tab": "Boards", "col": "handId", "drop": 1},
        {"tab": "HandsPlayers", "col": "handId", "drop": 1},
        {"tab": "HandsPlayers", "col": "playerId", "drop": 1},
        {"tab": "HandsPlayers", "col": "tourneysPlayersId", "drop": 0},
        {"tab": "HandsPlayers", "col": "startCards", "drop": 1},
        {"tab": "HudCache", "col": "gametypeId", "drop": 1},
        {"tab": "HudCache", "col": "playerId", "drop": 0},
        {"tab": "HudCache", "col": "tourneyTypeId", "drop": 0},
        {"tab": "Sessions", "col": "weekId", "drop": 1},
        {"tab": "Sessions", "col": "monthId", "drop": 1},
        {"tab": "SessionsCache", "col": "sessionId", "drop": 1},
        {"tab": "SessionsCache", "col": "gametypeId", "drop": 1},
        {"tab": "SessionsCache", "col": "playerId", "drop": 0},
        {"tab": "TourneysCache", "col": "sessionId", "drop": 1},
        {"tab": "TourneysCache", "col": "tourneyId", "drop": 1},
        {"tab": "TourneysCache", "col": "playerId", "drop": 0},
        {"tab": "Players", "col": "siteId", "drop": 1},
        # , {'tab':'Players',         'col':'name',              'drop':0}  unique indexes not dropped
        {"tab": "Tourneys", "col": "tourneyTypeId", "drop": 1},
        {"tab": "Tourneys", "col": "sessionId", "drop": 1},
        # , {'tab':'Tourneys',        'col':'siteTourneyNo',     'drop':0}  unique indexes not dropped
        {"tab": "TourneysPlayers", "col": "playerId", "drop": 0},
        # , {'tab':'TourneysPlayers', 'col':'tourneyId',         'drop':0}  unique indexes not dropped
        {"tab": "TourneyTypes", "col": "siteId", "drop": 0},
        {"tab": "Backings", "col": "tourneysPlayersId", "drop": 0},
        {"tab": "Backings", "col": "playerId", "drop": 0},
        {"tab": "RawHands", "col": "id", "drop": 0},
        {"tab": "RawTourneys", "col": "id", "drop": 0},
    ],
    [  # indexes for sqlite (list index 4)
        {"tab": "Hands", "col": "tourneyId", "drop": 0},
        {"tab": "Hands", "col": "gametypeId", "drop": 0},
        {"tab": "Hands", "col": "sessionId", "drop": 0},
        {"tab": "Hands", "col": "fileId", "drop": 0},
        {"tab": "Boards", "col": "handId", "drop": 0},
        {"tab": "Gametypes", "col": "siteId", "drop": 0},
        {"tab": "HandsPlayers", "col": "handId", "drop": 0},
        {"tab": "HandsPlayers", "col": "playerId", "drop": 0},
        {"tab": "HandsPlayers", "col": "tourneysPlayersId", "drop": 0},
        {"tab": "HandsActions", "col": "handId", "drop": 0},
        {"tab": "HandsActions", "col": "playerId", "drop": 0},
        {"tab": "HandsActions", "col": "actionId", "drop": 1},
        {"tab": "HandsActions", "col": "street", "drop": 1},
        {"tab": "HandsActions", "col": "actionType", "drop": 1},
        {"tab": "HandsStove", "col": "handId", "drop": 0},
        {"tab": "HandsStove", "col": "playerId", "drop": 0},
        {"tab": "HandsPots", "col": "handId", "drop": 0},
        {"tab": "HandsPots", "col": "playerId", "drop": 0},
        {"tab": "HudCache", "col": "gametypeId", "drop": 1},
        {"tab": "HudCache", "col": "playerId", "drop": 0},
        {"tab": "HudCache", "col": "tourneyTypeId", "drop": 0},
        {"tab": "Sessions", "col": "weekId", "drop": 1},
        {"tab": "Sessions", "col": "monthId", "drop": 1},
        {"tab": "SessionsCache", "col": "sessionId", "drop": 1},
        {"tab": "SessionsCache", "col": "gametypeId", "drop": 1},
        {"tab": "SessionsCache", "col": "playerId", "drop": 0},
        {"tab": "TourneysCache", "col": "sessionId", "drop": 1},
        {"tab": "TourneysCache", "col": "tourneyId", "drop": 1},
        {"tab": "TourneysCache", "col": "playerId", "drop": 0},
        {"tab": "Players", "col": "siteId", "drop": 1},
        {"tab": "Tourneys", "col": "tourneyTypeId", "drop": 1},
        {"tab": "Tourneys", "col": "sessionId", "drop": 1},
        {"tab": "TourneysPlayers", "col": "playerId", "drop": 0},
        {"tab": "TourneyTypes", "col": "siteId", "drop": 0},
        {"tab": "Backings", "col": "tourneysPlayersId", "drop": 0},
        {"tab": "Backings", "col": "playerId", "drop": 0},
        {"tab": "RawHands", "col": "id", "drop": 0},
        {"tab": "RawTourneys", "col": "id", "drop": 0},
    ],
]

FOREIGN_KEYS: list[list[dict[str, Any]]] = [
    [],  # no db with index 0
    [],  # no db with index 1
    [  # foreign keys for mysql (index 2)
        {
            "fktab": "Hands",
            "fkcol": "tourneyId",
            "rtab": "Tourneys",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Hands",
            "fkcol": "gametypeId",
            "rtab": "Gametypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Hands",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Hands",
            "fkcol": "fileId",
            "rtab": "Files",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Boards",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "tourneysPlayersId",
            "rtab": "TourneysPlayers",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "startCards",
            "rtab": "StartCards",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsActions",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsActions",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsActions",
            "fkcol": "actionId",
            "rtab": "Actions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsStove",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsStove",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsStove",
            "fkcol": "rankId",
            "rtab": "Rank",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPots",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPots",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HudCache",
            "fkcol": "gametypeId",
            "rtab": "Gametypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HudCache",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 0,
        },
        {
            "fktab": "HudCache",
            "fkcol": "tourneyTypeId",
            "rtab": "TourneyTypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Sessions",
            "fkcol": "weekId",
            "rtab": "Weeks",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Sessions",
            "fkcol": "monthId",
            "rtab": "Months",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "SessionsCache",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "SessionsCache",
            "fkcol": "gametypeId",
            "rtab": "Gametypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "SessionsCache",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 0,
        },
        {
            "fktab": "TourneysCache",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "TourneysCache",
            "fkcol": "tourneyId",
            "rtab": "Tourneys",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "TourneysCache",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 0,
        },
        {
            "fktab": "Tourneys",
            "fkcol": "tourneyTypeId",
            "rtab": "TourneyTypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Tourneys",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
    ],
    [  # foreign keys for postgres (index 3)
        {
            "fktab": "Hands",
            "fkcol": "tourneyId",
            "rtab": "Tourneys",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Hands",
            "fkcol": "gametypeId",
            "rtab": "Gametypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Hands",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Hands",
            "fkcol": "fileId",
            "rtab": "Files",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Boards",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "tourneysPlayersId",
            "rtab": "TourneysPlayers",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPlayers",
            "fkcol": "startCards",
            "rtab": "StartCards",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsActions",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsActions",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsActions",
            "fkcol": "actionId",
            "rtab": "Actions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsStove",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsStove",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsStove",
            "fkcol": "rankId",
            "rtab": "Rank",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPots",
            "fkcol": "handId",
            "rtab": "Hands",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HandsPots",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HudCache",
            "fkcol": "gametypeId",
            "rtab": "Gametypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "HudCache",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 0,
        },
        {
            "fktab": "HudCache",
            "fkcol": "tourneyTypeId",
            "rtab": "TourneyTypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Sessions",
            "fkcol": "weekId",
            "rtab": "Weeks",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Sessions",
            "fkcol": "monthId",
            "rtab": "Months",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "SessionsCache",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "SessionsCache",
            "fkcol": "gametypeId",
            "rtab": "Gametypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "SessionsCache",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 0,
        },
        {
            "fktab": "TourneysCache",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "TourneysCache",
            "fkcol": "tourneyId",
            "rtab": "Tourneys",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "TourneysCache",
            "fkcol": "playerId",
            "rtab": "Players",
            "rcol": "id",
            "drop": 0,
        },
        {
            "fktab": "Tourneys",
            "fkcol": "tourneyTypeId",
            "rtab": "TourneyTypes",
            "rcol": "id",
            "drop": 1,
        },
        {
            "fktab": "Tourneys",
            "fkcol": "sessionId",
            "rtab": "Sessions",
            "rcol": "id",
            "drop": 1,
        },
    ],
    [],  # no foreign keys in sqlite (index 4)
]


class DatabaseIndexesMixin:
    """Creates and drops the indexes and foreign keys of the catalogues above.

    Mixed into Database through DatabaseSchemaMixin.
    """

    # The per-backend catalogues this mixin applies. prepareBulkImport and
    # afterBulkImport, still on the host, read them through the MRO.
    indexes = INDEXES
    foreignKeys = FOREIGN_KEYS

    # Provided by Database.
    backend: int
    MYSQL_INNODB: int
    PGSQL: int
    SQLITE: int

    if TYPE_CHECKING:
        # Declared as callables rather than stub methods: pylint reads a stub's
        # empty body as a method that returns nothing.
        _pg_set_isolation: Callable[..., None]
        commit: Callable[..., None]
        get_cursor: Callable[..., Any]

    def drop_referential_integrity(self) -> None:
        """Update all tables to remove foreign keys (MySQL/MariaDB).

        Reads the constraint names from information_schema instead of guessing
        them from ``SHOW CREATE TABLE``: the old regex only matched the default
        ``<table>_ibfk_N`` names, so any explicitly named constraint survived
        and the subsequent DROP TABLE failed with errno 1451.
        """
        c = self.get_cursor()
        c.execute(
            "SELECT DISTINCT table_name, constraint_name "
            "FROM information_schema.table_constraints "
            "WHERE constraint_type = 'FOREIGN KEY' AND table_schema = DATABASE()",
        )
        constraints = c.fetchall()
        for table, constraint in constraints:
            c.execute(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{constraint}`")  # nosemgrep
        self.commit()

    # end drop_referential_inegrity

    def createAllIndexes(self) -> None:
        """Create new indexes."""
        if self.backend == self.PGSQL:
            self._pg_set_isolation(
                0,
            )  # allow table/index operations to work
        c = self.get_cursor()
        for idx in self.indexes[self.backend]:
            log.info(f"Creating index {idx['tab']} {idx['col']}")
            if self.backend == self.MYSQL_INNODB:
                s = "CREATE INDEX {} ON {}({})".format(idx["col"], idx["tab"], idx["col"])
                c.execute(s)  # nosemgrep
            elif self.backend in (self.PGSQL, self.SQLITE):
                s = "CREATE INDEX {}_{}_idx ON {}({})".format(
                    idx["tab"],
                    idx["col"],
                    idx["tab"],
                    idx["col"],
                )
                c.execute(s)  # nosemgrep

        if self.backend == self.PGSQL:
            self._pg_set_isolation(1)  # go back to normal isolation level

    # end def createAllIndexes

    def dropAllIndexes(self) -> int | None:
        """Drop all standalone indexes (i.e. not including primary keys or foreign keys)
        using list of indexes in indexes data structure.
        """
        # maybe upgrade to use data dictionary?? (but take care to exclude PK and FK)
        if self.backend == self.PGSQL:
            self._pg_set_isolation(
                0,
            )  # allow table/index operations to work
        for idx in self.indexes[self.backend]:
            if self.backend == self.MYSQL_INNODB:
                log.debug(f"Dropping index: {idx['tab']} {idx['col']}")
                try:
                    self.get_cursor().execute(
                        "alter table %s drop index %s",
                        (idx["tab"], idx["col"]),
                    )
                except Exception:  # intentional broad catch: drop index (MySQL) best-effort, continue
                    log.exception(f"Drop index failed: {sys.exc_info()}")
            elif self.backend == self.PGSQL:
                log.debug(f"Dropping index: {idx['tab']} {idx['col']}")
                # mod to use tab_col for index name?
                try:
                    self.get_cursor().execute(  # nosemgrep
                        "drop index {}_{}_idx".format(idx["tab"], idx["col"]),
                    )
                except Exception:  # intentional broad catch: drop index (PG) best-effort, continue
                    log.exception(f"Drop index failed: {sys.exc_info()}")
            elif self.backend == self.SQLITE:
                log.debug(f"Dropping index: {idx['tab']} {idx['col']}")
                try:
                    self.get_cursor().execute(  # nosemgrep
                        "drop index {}_{}_idx".format(idx["tab"], idx["col"]),
                    )
                except Exception:  # intentional broad catch: drop index (SQLite) best-effort, continue
                    log.exception(f"Drop index failed: {sys.exc_info()}")
            else:
                return -1
        if self.backend == self.PGSQL:
            self._pg_set_isolation(1)  # go back to normal isolation level
            return None
        return None

    # end def dropAllIndexes

    def createAllForeignKeys(self) -> None:
        """Create foreign keys."""
        try:
            if self.backend == self.PGSQL:
                self._pg_set_isolation(
                    0,
                )  # allow table/index operations to work
            c = self.get_cursor()
        except Exception:  # intentional broad catch: set_isolation_level (PG) best-effort before DDL
            log.exception(f"set_isolation_level failed: {sys.exc_info()}")

        for fk in self.foreignKeys[self.backend]:
            if self.backend == self.MYSQL_INNODB:
                c.execute(
                    "SELECT constraint_name "
                    "FROM information_schema.KEY_COLUMN_USAGE "
                    # "WHERE REFERENCED_TABLE_SCHEMA = 'fpdb'
                    "WHERE 1=1 "
                    "AND table_name = %s AND column_name = %s "
                    "AND referenced_table_name = %s "
                    "AND referenced_column_name = %s ",
                    (fk["fktab"], fk["fkcol"], fk["rtab"], fk["rcol"]),
                )
                cons = c.fetchone()
                # print "afterbulk: cons=", cons
                if cons:
                    pass
                else:
                    log.debug(
                        f"Creating foreign key: {fk['fktab']} {fk['fkcol']} -> {fk['rtab']} {fk['rcol']}",
                    )
                    try:
                        c.execute(  # nosemgrep
                            "alter table "
                            + fk["fktab"]
                            + " add foreign key ("
                            + fk["fkcol"]
                            + ") references "
                            + fk["rtab"]
                            + "("
                            + fk["rcol"]
                            + ")",
                        )
                    except Exception:  # intentional broad catch: create FK (MySQL) best-effort, continue
                        log.exception(f"Create foreign key failed: {sys.exc_info()}")
            elif self.backend == self.PGSQL:
                log.debug(
                    f"Creating foreign key: {fk['fktab']}.{fk['fkcol']} -> {fk['rtab']}.{fk['rcol']}",
                )
                try:
                    c.execute(  # nosemgrep
                        "alter table "
                        + fk["fktab"]
                        + " add constraint "
                        + fk["fktab"]
                        + "_"
                        + fk["fkcol"]
                        + "_fkey"
                        + " foreign key ("
                        + fk["fkcol"]
                        + ") references "
                        + fk["rtab"]
                        + "("
                        + fk["rcol"]
                        + ")",
                    )
                except Exception:  # intentional broad catch: create FK (PG) best-effort, continue
                    log.exception(f"Create foreign key failed: {sys.exc_info()!s}")
            else:
                pass

        try:
            if self.backend == self.PGSQL:
                self._pg_set_isolation(
                    1,
                )  # go back to normal isolation level
        except Exception:  # intentional broad catch: reset isolation_level (PG) best-effort after DDL
            log.exception(f"set_isolation_level failed: {sys.exc_info()!s}")

    # end def createAllForeignKeys

    def dropAllForeignKeys(self) -> None:
        """Drop all standalone indexes (i.e. not including primary keys or foreign keys)
        using list of indexes in indexes data structure.
        """
        # maybe upgrade to use data dictionary?? (but take care to exclude PK and FK)
        if self.backend == self.PGSQL:
            self._pg_set_isolation(
                0,
            )  # allow table/index operations to work
        c = self.get_cursor()

        for fk in self.foreignKeys[self.backend]:
            if self.backend == self.MYSQL_INNODB:
                c.execute(
                    "SELECT constraint_name "
                    "FROM information_schema.KEY_COLUMN_USAGE "
                    # "WHERE REFERENCED_TABLE_SHEMA = 'fpdb'
                    "WHERE 1=1 "
                    "AND table_name = %s AND column_name = %s "
                    "AND referenced_table_name = %s "
                    "AND referenced_column_name = %s ",
                    (fk["fktab"], fk["fkcol"], fk["rtab"], fk["rcol"]),
                )
                cons = c.fetchone()
                # print "preparebulk find fk: cons=", cons
                if cons:
                    log.debug(
                        f"Dropping foreign key: {cons[0]} {fk['fktab']}.{fk['fkcol']}",
                    )
                    try:
                        c.execute(  # nosemgrep
                            "alter table " + fk["fktab"] + " drop foreign key " + cons[0],
                        )
                    except Exception:  # intentional broad catch: drop FK (MySQL) best-effort, continue
                        log.exception(
                            f"Warning: Drop foreign key {fk['fktab']}_{fk['fkcol']}_fkey failed: {str(sys.exc_info()[1]).rstrip('')}, continuing ...",
                        )
            elif self.backend == self.PGSQL:
                #    DON'T FORGET TO RECREATE THEM!!
                log.debug(f"Dropping foreign key: {fk['fktab']}.{fk['fkcol']}")
                try:
                    # try to lock table to see if index drop will work:
                    # hmmm, tested by commenting out rollback in grapher. lock seems to work but
                    # then drop still hangs :-(  does work in some tests though??
                    # will leave code here for now pending further tests/enhancement ...
                    c.execute("BEGIN TRANSACTION")
                    c.execute("lock table {} in exclusive mode nowait".format(fk["fktab"]))  # nosemgrep
                    # print "after lock, status:", c.statusmessage
                    # print "alter table %s drop constraint %s_%s_fkey" % (fk['fktab'], fk['fktab'], fk['fkcol'])
                    try:
                        c.execute(  # nosemgrep
                            "alter table {} drop constraint {}_{}_fkey".format(fk["fktab"], fk["fktab"], fk["fkcol"]),
                        )
                        log.debug(
                            f"dropped foreign key {fk['fktab']}_{fk['fkcol']}_fkey, continuing ...",
                        )
                    except Exception:  # intentional broad catch: drop FK constraint (PG) ignores 'does not exist'
                        if "does not exist" not in str(sys.exc_info()[1]):
                            log.exception(
                                f"Drop foreign key {fk['fktab']}_{fk['fkcol']}_fkey failed: {str(sys.exc_info()[1]).rstrip('')}, continuing ...",
                            )
                    c.execute("END TRANSACTION")
                except Exception:  # intentional broad catch: drop FK (PG lock/txn) best-effort, continue
                    log.exception(
                        f"Constraint {fk['fktab']}_{fk['fkcol']}_fkey not dropped: {str(sys.exc_info()[1]).rstrip('')}, continuing ...",
                    )
            else:
                # print ("Only MySQL and Postgres supported so far")
                pass

        if self.backend == self.PGSQL:
            self._pg_set_isolation(1)  # go back to normal isolation level

    # end def dropAllForeignKeys

    def rebuild_indexes(self, start: Any = None) -> None:
        self.dropAllIndexes()
        self.createAllIndexes()
        self.dropAllForeignKeys()
        self.createAllForeignKeys()

    # end def rebuild_indexes
