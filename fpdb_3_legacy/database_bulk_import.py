"""Bulk-import buffers and their flush for the fpdb database.

Split out of Database.py: these methods own the per-import buffers -- one list
or dict per table -- filled while a file is parsed and written in one go when
the last hand of the batch arrives. prepareBulkImport and afterBulkImport
bracket a mass import, dropping and restoring indexes and foreign keys around
it.

The mixin owns the buffers: resetBulkCache creates every one of them. Its
borrowings from the host are declared below.
"""

from __future__ import annotations

import csv
import os
import random
import re
import string
import sys
from datetime import datetime
from time import time
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.database_schema import HANDS_PLAYERS_KEYS
from fpdb_3_legacy.Exceptions import FpdbError
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db")

re_insert = re.compile(
    r"insert\sinto\s(?P<TABLENAME>[A-Za-z]+)\s(?P<COLUMNS>\(.+?\))\s+values",
    re.DOTALL,
)


class DatabaseBulkImportMixin:
    """Accumulates one import's rows and writes them in bulk.

    Mixed into Database, which supplies the connection, the query catalogue and
    the backend identity named below. The index and foreign-key catalogues come
    from DatabaseSchemaMixin through the MRO.
    """

    # Provided by Database.
    sql: Any
    config: Any
    backend: int
    import_options: dict[str, Any]
    MYSQL_INNODB: int
    PGSQL: int
    indexes: list[list[dict[str, Any]]]
    foreignKeys: list[list[dict[str, Any]]]

    # Created by resetBulkCache, below, and read by the cache and tournament
    # mixins as well as by the host.
    siteHandNos: list[Any]
    hbulk: list[Any]
    bbulk: list[Any]
    hpbulk: list[Any]
    habulk: list[Any]
    hcbulk: dict[Any, Any]
    dcbulk: dict[Any, Any]
    pcbulk: dict[Any, Any]
    hsbulk: list[Any]
    hsdbulk: list[Any]
    hcobulk: list[Any]
    panbulk: list[Any]
    htbulk: list[Any]
    tbulk: dict[Any, Any]
    s: dict[str, Any]
    sc: dict[Any, Any]
    tc: dict[Any, Any]
    hids: list[Any]

    if TYPE_CHECKING:

        def get_cursor(self, connect: bool = False) -> Any: ...

        def commit(self, force: bool = False) -> None: ...

        def get_last_insert_id(self, cursor: Any = None) -> Any: ...

        def do_connect(self, config: Any) -> None: ...

        def updateTourneysSessions(self) -> None: ...

        def _pg_set_isolation(self, level: int) -> None: ...

        # From DatabaseCachesMixin, which resolves the session of each hand.
        def appendHandsSessionIds(self) -> None: ...


    def prepareBulkImport(self) -> int | None:
        """Drop some indexes/foreign keys to prepare for bulk import.
        Currently keeping the standalone indexes as needed to import quickly.
        """
        stime = time()
        c = self.get_cursor()
        # sc: don't think autocommit=0 is needed, should already be in that mode
        if self.backend == self.MYSQL_INNODB:
            c.execute("SET foreign_key_checks=0")
            c.execute("SET autocommit=0")
            return None
        if self.backend == self.PGSQL:
            self._pg_set_isolation(
                0,
            )  # allow table/index operations to work
        for fk in self.foreignKeys[self.backend]:
            if fk["drop"] == 1:
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
                    # print "preparebulk find fk: cons=", cons
                    if cons:
                        log.debug(
                            f"dropping mysql fk {cons[0]} {fk['fktab']} {fk['fkcol']}",
                        )
                        try:
                            c.execute(
                                "alter table " + fk["fktab"] + " drop foreign key " + cons[0],
                            )
                        except (
                            Exception
                        ):  # intentional broad catch: cross-backend FK drop (MySQL) best-effort, continue
                            log.exception(f"    drop failed: {sys.exc_info()}")
                elif self.backend == self.PGSQL:
                    #    DON'T FORGET TO RECREATE THEM!!
                    log.debug(f"dropping pg fk {fk['fktab']} {fk['fkcol']}")
                    try:
                        # try to lock table to see if index drop will work:
                        # hmmm, tested by commenting out rollback in grapher. lock seems to work but
                        # then drop still hangs :-(  does work in some tests though??
                        # will leave code here for now pending further tests/enhancement ...
                        c.execute("BEGIN TRANSACTION")
                        c.execute(
                            "lock table {} in exclusive mode nowait".format(fk["fktab"]),
                        )
                        # print "after lock, status:", c.statusmessage
                        # print "alter table %s drop constraint %s_%s_fkey" % (fk['fktab'], fk['fktab'], fk['fkcol'])
                        try:
                            c.execute(
                                "alter table {} drop constraint {}_{}_fkey".format(
                                    fk["fktab"], fk["fktab"], fk["fkcol"]
                                ),
                            )
                            log.debug(f"dropping pg fk {fk['fktab']} {fk['fkcol']}")
                        except (
                            Exception
                        ):  # intentional broad catch: cross-backend FK drop (PG) ignores 'does not exist'
                            if "does not exist" not in str(sys.exc_info()[1]):
                                log.exception(
                                    f"warning: drop pg fk {fk['fktab']}_{fk['fkcol']}_fkey failed: {str(sys.exc_info()[1]).rstrip()}, continuing ...",
                                )
                        c.execute("END TRANSACTION")
                    except (
                        Exception
                    ):  # intentional broad catch: cross-backend FK drop (PG lock/txn) best-effort, continue
                        log.exception(
                            rf"warning: constraint {fk['fktab']}_{fk['fkcol']}_fkey not dropped: {str(sys.exc_info()[1]).rstrip('')}, continuing ...",
                        )
                else:
                    return -1

        for idx in self.indexes[self.backend]:
            if idx["drop"] == 1:
                if self.backend == self.MYSQL_INNODB:
                    log.info(f"dropping mysql index {idx['tab']} {idx['col']}")
                    try:
                        # apparently nowait is not implemented in mysql so this just hangs if there are locks
                        # preventing the index drop :-(
                        c.execute(
                            "alter table %s drop index %s;",
                            (idx["tab"], idx["col"]),
                        )
                    except Exception:  # intentional broad catch: cross-backend index drop (MySQL) best-effort, continue
                        log.exception(f"    drop index failed: {sys.exc_info()}")
                        # ALTER TABLE `fpdb`.`handsplayers` DROP INDEX `playerId`;
                        # using: 'HandsPlayers' drop index 'playerId'
                elif self.backend == self.PGSQL:
                    #    DON'T FORGET TO RECREATE THEM!!
                    log.info(f"dropping pg index {idx['tab']} {idx['col']}")
                    try:
                        # try to lock table to see if index drop will work:
                        c.execute("BEGIN TRANSACTION")
                        c.execute(
                            "lock table {} in exclusive mode nowait".format(idx["tab"]),
                        )
                        # print "after lock, status:", c.statusmessage
                        try:
                            # table locked ok so index drop should work:
                            # print "drop index %s_%s_idx" % (idx['tab'],idx['col'])
                            c.execute(
                                "drop index if exists {}_{}_idx".format(idx["tab"], idx["col"]),
                            )
                            # print "dropped  pg index ", idx['tab'], idx['col']
                        except (
                            Exception
                        ):  # intentional broad catch: cross-backend index drop (PG) ignores 'does not exist'
                            if "does not exist" not in str(sys.exc_info()[1]):
                                log.exception(
                                    f"drop index {idx['tab']}_{idx['col']}_idx failed: {str(sys.exc_info()[1]).rstrip('')}, continuing ...",
                                )
                        c.execute("END TRANSACTION")
                    except (
                        Exception
                    ):  # intentional broad catch: cross-backend index drop (PG lock/txn) best-effort, continue
                        log.exception(
                            f"index {idx['tab']}_{idx['col']}_idx not dropped {str(sys.exc_info()[1]).rstrip('')}, continuing ...",
                        )
                else:
                    return -1

        if self.backend == self.PGSQL:
            self._pg_set_isolation(1)  # go back to normal isolation level
        self.commit()  # seems to clear up errors if there were any in postgres
        ptime = time() - stime
        log.debug(f"prepare import took {ptime} seconds")
        return None

    # end def prepareBulkImport

    def afterBulkImport(self) -> int | None:
        """Re-create any dropped indexes/foreign keys after bulk import."""
        stime = time()

        c = self.get_cursor()
        if self.backend == self.MYSQL_INNODB:
            c.execute("SET foreign_key_checks=1")
            c.execute("SET autocommit=1")
            return None

        if self.backend == self.PGSQL:
            self._pg_set_isolation(
                0,
            )  # allow table/index operations to work
        for fk in self.foreignKeys[self.backend]:
            if fk["drop"] == 1:
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
                            f"Creating foreign key {fk['fktab']}.{fk['fkcol']} -> {fk['rtab']}.{fk['rcol']}",
                        )
                        try:
                            c.execute(
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
                        except (
                            Exception
                        ):  # intentional broad catch: cross-backend FK create (MySQL) best-effort, continue
                            log.exception(f"Create foreign key failed: {sys.exc_info()}")
                elif self.backend == self.PGSQL:
                    log.debug(
                        f"Creating foreign key {fk['fktab']}.{fk['fkcol']} -> {fk['rtab']}.{fk['rcol']}",
                    )
                    try:
                        c.execute(
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
                    except Exception:  # intentional broad catch: cross-backend FK create (PG) best-effort, continue
                        log.exception(f"Create foreign key failed: {sys.exc_info()}")
                else:
                    return -1

        for idx in self.indexes[self.backend]:
            if idx["drop"] == 1:
                if self.backend == self.MYSQL_INNODB:
                    log.debug(f"Creating MySQL index {idx['tab']} {idx['col']}")
                    try:
                        s = "alter table {} add index {}({})".format(
                            idx["tab"],
                            idx["col"],
                            idx["col"],
                        )
                        c.execute(s)
                    except (
                        Exception
                    ):  # intentional broad catch: cross-backend index create (MySQL) best-effort, continue
                        log.exception(f"Create foreign key failed: {sys.exc_info()}")
                elif self.backend == self.PGSQL:
                    #                pass
                    # mod to use tab_col for index name?
                    log.debug(f"Creating PostgreSQL index {idx['tab']} {idx['col']}")
                    try:
                        s = "create index {}_{}_idx on {}({})".format(
                            idx["tab"],
                            idx["col"],
                            idx["tab"],
                            idx["col"],
                        )
                        c.execute(s)
                    except Exception:  # intentional broad catch: cross-backend index create (PG) best-effort, continue
                        log.exception(f"Create index failed: {sys.exc_info()}")
                else:
                    return -1

        if self.backend == self.PGSQL:
            self._pg_set_isolation(1)  # go back to normal isolation level
        self.commit()  # seems to clear up errors if there were any in postgres
        atime = time() - stime
        log.debug(f"After import took {atime} seconds")
        return None

    # end def afterBulkImport

    def resetBulkCache(self, reconnect=False) -> None:
        self.siteHandNos: list[Any] = []  # cache of siteHandNo
        self.hbulk: list[Any] = []  # Hands bulk inserts
        self.bbulk: list[Any] = []  # Boards bulk inserts
        self.hpbulk: list[Any] = []  # HandsPlayers bulk inserts
        self.habulk: list[Any] = []  # HandsActions bulk inserts
        self.hcbulk: dict[Any, Any] = {}  # HudCache bulk inserts
        self.dcbulk: dict[Any, Any] = {}  # CardsCache bulk inserts
        self.pcbulk: dict[Any, Any] = {}  # PositionsCache bulk inserts
        self.hsbulk: list[Any] = []  # HandsStove bulk inserts
        self.hsdbulk: list[Any] = []  # HandsShowdown bulk inserts
        self.hcobulk: list[Any] = []  # HandsCashout bulk inserts
        self.panbulk: list[Any] = []  # PlayerAutoNotes bulk upserts
        self.htbulk: list[Any] = []  # HandsPots bulk inserts
        self.tbulk: dict[Any, Any] = {}  # Tourneys bulk updates
        self.s: dict[str, Any] = {"bk": []}  # Sessions bulk updates
        self.sc: dict[Any, Any] = {}  # SessionsCache bulk updates
        self.tc: dict[Any, Any] = {}  # TourneysCache bulk updates
        self.hids: list[Any] = []  # hand ids in order of hand bulk inserts
        # self.tids        = []         # tourney ids in order of hp bulk inserts
        if reconnect:
            self.do_connect(self.config)

    def executemany(self, c, q, values) -> None:
        if self.backend == self.PGSQL and self.import_options["hhBulkPath"] != "":
            # COPY much faster under postgres. Requires superuser privileges
            m = re_insert.match(q)
            if m is None:
                raise FpdbError(f"Unable to derive a COPY statement from query: {q}")
            rand = "".join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(5))
            bulk_file = os.path.join(
                self.import_options["hhBulkPath"],
                m.group("TABLENAME") + "_" + rand,
            )
            with open(bulk_file, "w", encoding="utf-8", newline="") as csvfile:
                writer = csv.writer(
                    csvfile,
                    delimiter="\t",
                    quotechar='"',
                    quoting=csv.QUOTE_MINIMAL,
                )
                writer.writerows(w for w in values)
            q_insert = (
                "COPY " + m.group("TABLENAME") + m.group("COLUMNS") + " FROM '" + bulk_file + "' DELIMITER '\t' CSV"
            )
            c.execute(q_insert)
            os.remove(bulk_file)
        else:
            batch_size = 20000  # experiment to find optimal batch_size for your data
            while values:  # repeat until all records in values have been inserted ''
                batch, values = (
                    values[:batch_size],
                    values[batch_size:],
                )  # split values into the current batch and the remaining records
                c.executemany(q, batch)  # insert current batch ''

    def storeHand(self, hdata, doinsert=False, printdata=False) -> None:
        if printdata:
            log.debug("######## Hands ##########")
            import pprint

            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(hdata)
            log.debug("###### End Hands ########")

        # Tablename can have odd charachers
        # hdata["tableName"] = Charset.to_db_utf8(hdata["tableName"])[:50]
        table_name = hdata.get("tableName", "")
        table_name_safe = table_name.encode("utf-8", "replace").decode("utf-8")
        hdata["tableName"] = table_name_safe[:50]

        self.hids.append(hdata["id"])
        self.hbulk.append(
            [
                hdata["id"],
                hdata["tableName"],
                hdata["siteHandNo"],
                hdata["tourneyId"],
                hdata["gametypeId"],
                hdata["sessionId"],
                hdata["fileId"],
                hdata["startTime"].replace(tzinfo=None),
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),  # importtime
                hdata["seats"],
                hdata["heroSeat"],
                hdata["maxPosition"],
                hdata["texture"],
                hdata["playersVpi"],
                hdata["boardcard1"],
                hdata["boardcard2"],
                hdata["boardcard3"],
                hdata["boardcard4"],
                hdata["boardcard5"],
                hdata["runItTwice"],
                hdata["playersAtStreet1"],
                hdata["playersAtStreet2"],
                hdata["playersAtStreet3"],
                hdata["playersAtStreet4"],
                hdata["playersAtShowdown"],
                hdata["street0Raises"],
                hdata["street1Raises"],
                hdata["street2Raises"],
                hdata["street3Raises"],
                hdata["street4Raises"],
                hdata["street0Pot"],
                hdata["street1Pot"],
                hdata["street2Pot"],
                hdata["street3Pot"],
                hdata["street4Pot"],
                hdata["finalPot"],
                hdata.get("bombPot", 0),
                hdata.get("splashPot", 0),
            ],
        )

        if doinsert:
            self.appendHandsSessionIds()
            self.updateTourneysSessions()
            q = self.sql.query["store_hand"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            c.executemany(q, self.hbulk)
            self.commit()

    def storeBoards(self, id, boards, doinsert) -> None:
        if boards:
            for b in boards:
                self.bbulk += [[id, *b]]
        if doinsert and self.bbulk:
            q = self.sql.query["store_boards"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            self.executemany(c, q, self.bbulk)  # c.executemany(q, self.bbulk)

    def storeHandsPlayers(self, hid, pids, pdata, doinsert=False, printdata=False) -> None:
        log.info(
            f"Entering storeHandsPlayers: hid={hid}, doinsert={doinsert}, printdata={printdata}",
        )

        if printdata:
            import pprint

            pp = pprint.PrettyPrinter(indent=4)
            log.debug("Printing pdata for debugging:")
            pp.pprint(pdata)

        hpbulk = self.hpbulk
        log.debug(f"Initialized hpbulk with current size: {len(hpbulk)}")

        for p, pvalue in pdata.items():
            log.debug(f"Processing player: {p}")
            try:
                bulk_data = [pvalue[key] for key in HANDS_PLAYERS_KEYS]
                bulk_data.append(pids[p])
                bulk_data.append(hid)
                bulk_data.reverse()
                hpbulk.append(bulk_data)
                log.debug(f"Appended data for player {p}: {bulk_data}")
            except KeyError as e:
                log.exception(f"Key error when processing player {p}. Missing key: {e}")
                raise

        log.debug(f"Final hpbulk size after processing: {len(hpbulk)}")

        if doinsert:
            log.info("Performing database insertion for hands_players data.")
            try:
                q = self.sql.query["store_hands_players"]
                q = q.replace("%s", self.sql.query["placeholder"])
                c = self.get_cursor(True)
                self.executemany(c, q, self.hpbulk)
                log.info(
                    f"Successfully inserted {len(self.hpbulk)} rows into hands_players.",
                )
            except Exception as e:  # intentional broad catch: hands_players bulk insert logs then re-raises
                log.exception(f"Error during database insertion in storeHandsPlayers: {e}")
                raise
        else:
            log.info("Skipping database insertion as doinsert=False.")

        log.info("Exiting storeHandsPlayers.")

    def storeHandsPots(self, tdata, doinsert) -> None:
        self.htbulk += tdata
        if doinsert and self.htbulk:
            q = self.sql.query["store_hands_pots"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            self.executemany(c, q, self.htbulk)  # c.executemany(q, self.hsbulk)

    def storeHandsActions(self, hid, pids, adata, doinsert=False, printdata=False) -> None:
        # print "DEBUG: %s %s %s" %(hid, pids, adata)

        # This can be used to generate test data. Currently unused
        # if printdata:
        #    import pprint
        #    pp = pprint.PrettyPrinter(indent=4)
        #    pp.pprint(adata)

        for a in adata:
            self.habulk.append(
                (
                    hid,
                    pids[adata[a]["player"]],
                    adata[a]["street"],
                    adata[a]["actionNo"],
                    adata[a]["streetActionNo"],
                    adata[a]["actionId"],
                    adata[a]["amount"],
                    adata[a]["raiseTo"],
                    adata[a]["amountCalled"],
                    adata[a]["numDiscarded"],
                    adata[a]["cardsDiscarded"],
                    adata[a]["allIn"],
                ),
            )

        if doinsert:
            q = self.sql.query["store_hands_actions"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            self.executemany(c, q, self.habulk)  # c.executemany(q, self.habulk)

    def storeHandsStove(self, sdata, doinsert) -> None:
        self.hsbulk += sdata
        if doinsert and self.hsbulk:
            q = self.sql.query["store_hands_stove"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            self.executemany(c, q, self.hsbulk)  # c.executemany(q, self.hsbulk)

    def storeHandsShowdown(self, sdata, doinsert) -> None:
        """Persist parsed showdown combinations (and winning cards) per player."""
        self.hsdbulk += sdata
        if doinsert and self.hsdbulk:
            q = self.sql.query["store_hands_showdown"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            self.executemany(c, q, self.hsdbulk)

    def storeHandsCashout(self, sdata, doinsert) -> None:
        """Persist per-player cashout amounts/fees."""
        self.hcobulk += sdata
        if doinsert and self.hcobulk:
            q = self.sql.query["store_hands_cashout"]
            q = q.replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            self.executemany(c, q, self.hcobulk)

    def storeFile(self, fdata):
        q = self.sql.query["store_file"]
        q = q.replace("%s", self.sql.query["placeholder"])
        c = self.get_cursor()
        c.execute(q, fdata)
        return self.get_last_insert_id(c)
