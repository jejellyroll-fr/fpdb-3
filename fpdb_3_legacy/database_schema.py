"""Schema construction and reference data for the fpdb database.

Split out of Database.py: these methods create and drop the tables and seed the
reference rows every fresh database needs. Bringing an older database up to date is
in database_migrations; indexes and foreign keys are in database_indexes. Both are
bases of DatabaseSchemaMixin, and the names they define stay importable from here.

The mixin borrows connection and cursor handling from its host; the borrowings
are declared below so the coupling is visible.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy import Card
from fpdb_3_legacy.database_indexes import FOREIGN_KEYS as FOREIGN_KEYS
from fpdb_3_legacy.database_indexes import INDEXES as INDEXES
from fpdb_3_legacy.database_indexes import DatabaseIndexesMixin
from fpdb_3_legacy.database_migrations import ACTION_ENUM_COLUMNS as ACTION_ENUM_COLUMNS
from fpdb_3_legacy.database_migrations import COLUMN_COLLATION_MYSQL as COLUMN_COLLATION_MYSQL
from fpdb_3_legacy.database_migrations import COLUMN_COLLATION_SQL as COLUMN_COLLATION_SQL
from fpdb_3_legacy.database_migrations import COLUMN_WIDTH_MYSQL as COLUMN_WIDTH_MYSQL
from fpdb_3_legacy.database_migrations import COLUMN_WIDTH_SQL as COLUMN_WIDTH_SQL
from fpdb_3_legacy.database_migrations import DDL_LOCK_TIMEOUT_MS as DDL_LOCK_TIMEOUT_MS
from fpdb_3_legacy.database_migrations import GAMETYPE_CATEGORY_WIDTH as GAMETYPE_CATEGORY_WIDTH
from fpdb_3_legacy.database_migrations import HANDS_ACTIONS_EVENT_DEFINITIONS as HANDS_ACTIONS_EVENT_DEFINITIONS
from fpdb_3_legacy.database_migrations import HANDS_PLAYERS_KEYS as HANDS_PLAYERS_KEYS
from fpdb_3_legacy.database_migrations import PGSQL_BINARY_COLLATIONS as PGSQL_BINARY_COLLATIONS
from fpdb_3_legacy.database_migrations import RESET_MYSQL_LOCK_TIMEOUT as RESET_MYSQL_LOCK_TIMEOUT
from fpdb_3_legacy.database_migrations import RESET_PGSQL_LOCK_TIMEOUT as RESET_PGSQL_LOCK_TIMEOUT
from fpdb_3_legacy.database_migrations import SET_MYSQL_LOCK_TIMEOUT as SET_MYSQL_LOCK_TIMEOUT
from fpdb_3_legacy.database_migrations import SET_PGSQL_LOCK_TIMEOUT as SET_PGSQL_LOCK_TIMEOUT
from fpdb_3_legacy.database_migrations import SET_PLAYERS_NAME_COLLATION_MYSQL as SET_PLAYERS_NAME_COLLATION_MYSQL
from fpdb_3_legacy.database_migrations import SET_PLAYERS_NAME_COLLATION_PGSQL as SET_PLAYERS_NAME_COLLATION_PGSQL
from fpdb_3_legacy.database_migrations import WIDEN_GAMETYPE_CATEGORY_MYSQL as WIDEN_GAMETYPE_CATEGORY_MYSQL
from fpdb_3_legacy.database_migrations import WIDEN_GAMETYPE_CATEGORY_SQL as WIDEN_GAMETYPE_CATEGORY_SQL
from fpdb_3_legacy.database_migrations import DatabaseMigrationsMixin
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db")

# Schema version written into Settings by create_tables and checked on connect.
DB_VERSION = 224


class DatabaseSchemaMixin(DatabaseMigrationsMixin, DatabaseIndexesMixin):
    """Builds the schema and seeds its reference data.

    Mixed into Database, which supplies the connection, the query catalogue and
    the backend identity named below.
    """

    # Provided by Database.
    sql: Any
    backend: int
    publicDB: bool

    if TYPE_CHECKING:
        # Declared as callables rather than stub methods: pylint reads a stub's
        # empty body as a method that returns nothing.
        commit: Callable[..., None]
        get_cursor: Callable[..., Any]
        get_sites: Callable[..., None]
        resetBulkCache: Callable[..., None]
        resetCache: Callable[..., None]

    def recreate_tables(self) -> None:
        """(Re-)creates the tables of the current DB."""
        self.drop_tables()
        self.resetCache()
        self.resetBulkCache()
        self.create_tables()
        self.createAllIndexes()
        self.commit()
        # A recreated database is born current: everything in it will be
        # written by the running code, so the extractor versions can be
        # stamped now and the rebuild tool can trust the record (#305).
        from fpdb_3_legacy import analytics_lifecycle

        analytics_lifecycle.bootstrap_meta(self)
        self.get_sites()
        log.info("Finished recreating tables")

    # end def recreate_tables

    def create_tables(self) -> None:
        log.debug(f"{self.sql.query['createSettingsTable']}")
        c = self.get_cursor()
        c.execute(self.sql.query["createSettingsTable"])

        log.debug("Creating tables")
        c.execute(self.sql.query["createActionsTable"])
        c.execute(self.sql.query["createRankTable"])
        c.execute(self.sql.query["createStartCardsTable"])
        c.execute(self.sql.query["createSitesTable"])
        c.execute(self.sql.query["createGametypesTable"])
        c.execute(self.sql.query["createFilesTable"])
        c.execute(self.sql.query["createPlayersTable"])
        c.execute(self.sql.query["createAutoratesTable"])
        c.execute(self.sql.query["createWeeksTable"])
        c.execute(self.sql.query["createMonthsTable"])
        c.execute(self.sql.query["createSessionsTable"])
        c.execute(self.sql.query["createTourneyTypesTable"])
        c.execute(self.sql.query["createTourneysTable"])
        c.execute(self.sql.query["createTourneysPlayersTable"])
        c.execute(self.sql.query["createTourneyPayoutsTable"])
        c.execute(self.sql.query["createActionBubbleFactorsTable"])
        c.execute(self.sql.query["createSessionsCacheTable"])
        c.execute(self.sql.query["createTourneysCacheTable"])
        c.execute(self.sql.query["createHandsTable"])
        c.execute(self.sql.query["createHandsPlayersTable"])
        c.execute(self.sql.query["createHandsActionsTable"])
        c.execute(self.sql.query["createHandsStoveTable"])
        c.execute(self.sql.query["createHandsShowdownTable"])
        c.execute(self.sql.query["createHandsCashoutTable"])
        c.execute(self.sql.query["createHandsSituationsTable"])
        c.execute(self.sql.query["createHandStatesTable"])
        c.execute(self.sql.query["createPlayerAutoNotesTable"])
        c.execute(self.sql.query["createAofDecisionsTable"])
        c.execute(self.sql.query["createAofDecisionAnalysesTable"])
        c.execute(self.sql.query["createHandsPotsTable"])
        c.execute(self.sql.query["createBoardFeaturesTable"])
        c.execute(self.sql.query["createHudCacheTable"])
        c.execute(self.sql.query["createCardsCacheTable"])
        c.execute(self.sql.query["createPositionsCacheTable"])
        c.execute(self.sql.query["createBoardsTable"])
        c.execute(self.sql.query["createBackingsTable"])
        c.execute(self.sql.query["createRawHands"])
        c.execute(self.sql.query["createRawTourneys"])

        # Create unique indexes:
        log.debug("Creating unique indexes")
        c.execute(self.sql.query["addTourneyIndex"])
        c.execute(
            self.sql.query["addHandsIndex"].replace(
                "<heroseat>",
                ", heroSeat" if self.publicDB else "",
            ),
        )
        c.execute(self.sql.query["addPlayersIndex"])
        c.execute(self.sql.query["addTPlayersIndex"])
        c.execute(self.sql.query["addPlayersSeat"])
        c.execute(self.sql.query["addHeroSeat"])
        c.execute(self.sql.query["addStartCardsIndex"])
        c.execute(self.sql.query["addSeatsIndex"])
        c.execute(self.sql.query["addPositionIndex"])
        # The feature tables created above index the same way the migration
        # path does, so a database built from scratch is not left doing full
        # scans until someone happens to reconnect with an older schema.
        c.execute(self.sql.query["addBoardFeaturesHandIndex"])
        c.execute(self.sql.query["addBoardFeaturesTextureIndex"])
        c.execute(self.sql.query["addPlayerAutoNotesPlayerIndex"])
        c.execute(self.sql.query["addPlayerAutoNotesHandIndex"])
        c.execute(self.sql.query["addPlayerAutoNotesRuleIndex"])
        c.execute(self.sql.query["addAofDecisionsPlayerIndex"])
        c.execute(self.sql.query["addAofDecisionsHandIndex"])
        c.execute(self.sql.query["addAofDecisionsRangeIndex"])
        c.execute(self.sql.query["addAofAnalysesDecisionIndex"])
        c.execute(self.sql.query["addAofAnalysesStatusIndex"])
        if "addActionBubbleFactorsTourneyIndex" in self.sql.query:  # MySQL declares it in the table
            c.execute(self.sql.query["addActionBubbleFactorsTourneyIndex"])
        c.execute(self.sql.query["addFilesIndex"])
        c.execute(self.sql.query["addTableNameIndex"])
        c.execute(self.sql.query["addPlayerNameIndex"])
        c.execute(self.sql.query["addPlayerHeroesIndex"])
        c.execute(self.sql.query["addStartCashIndex"])
        c.execute(self.sql.query["addEffStackIndex"])
        c.execute(self.sql.query["addTotalProfitIndex"])
        c.execute(self.sql.query["addWinningsIndex"])
        c.execute(self.sql.query["addFinalPotIndex"])
        c.execute(self.sql.query["addStreetIndex"])
        c.execute(self.sql.query["addSessionsCacheCompundIndex"])
        c.execute(self.sql.query["addTourneysCacheCompundIndex"])
        c.execute(self.sql.query["addHudCacheCompundIndex"])
        c.execute(self.sql.query["addCardsCacheCompundIndex"])
        c.execute(self.sql.query["addPositionsCacheCompundIndex"])

        self.fillDefaultData()
        self.commit()

    def drop_tables(self) -> None:
        """Drops the fpdb tables from the current db.

        Delegates to the backend Dialect, which drops every table whatever the
        foreign-key order is (FK checks off on MySQL/SQLite, CASCADE on
        PostgreSQL). The previous MySQL path relied on
        ``drop_referential_integrity`` removing the constraints one by one and
        failed with "Cannot delete or update a parent row: a foreign key
        constraint fails" (errno 1451) as soon as one constraint was not named
        ``<table>_ibfk_N``; the error was then swallowed, leaving tables behind
        and making the following ``create_tables`` fail in turn.
        """
        from fpdb_3_legacy import dialects

        dialects.dialect_for_backend(self.backend).drop_all_tables(self)

    # end def drop_tables

    def fillDefaultData(self) -> None:
        c = self.get_cursor()
        c.execute(f"INSERT INTO Settings (version) VALUES ({DB_VERSION});")
        # Fill Sites
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('1', 'Full Tilt Poker', 'FT')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('2', 'PokerStars', 'PS')")
        # PokerStars variants
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('32', 'PokerStars.COM', 'PS')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('33', 'PokerStars.FR', 'PS')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('34', 'PokerStars.IT', 'PS')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('35', 'PokerStars.ES', 'PS')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('36', 'PokerStars.PT', 'PS')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('37', 'PokerStars.EU', 'PS')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('130', 'PokerStars.DE', 'PS')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('3', 'Everleaf', 'EV')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('4', 'Boss', 'BM')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('5', 'OnGame', 'OG')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('6', 'UltimateBet', 'UB')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('7', 'Betfair', 'BF')")
        # c.execute("INSERT INTO Sites (id,name,code) VALUES ('8', 'Absolute', 'AB')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('9', 'PartyPoker', 'PP')")
        # PartyPoker variants
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('38', 'Party Poker', 'PP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('39', 'Bwin Poker', 'PP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('40', 'Bwin.fr Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('41', 'Bwin.it Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('42', 'Bwin.es Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('43', 'Bwin.de Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('44', 'PartyPoker.fr', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('45', 'PartyPoker.it', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('46', 'PartyPoker.es', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('47', 'PartyPoker.de', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('48', 'Empire Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('49', 'Gamebookers Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('50', 'Intertops Poker', 'PP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('51', 'MultiPoker', 'PP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('52', 'PokerRoom', 'PP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('53', 'PartyPoker NJ', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('54', 'BorgataPoker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('55', 'Borgata Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('120', 'WPT Poker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('121', 'WPTPoker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('122', 'PartyPoker.pt', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('123', 'PartyPoker.com', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('124', 'PartyPoker.eu', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('125', 'partycasino', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('126', 'PartyCasino', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('127', 'partypoker', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('128', 'bwin', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('129', 'PMU Poker (PartyPoker)', 'PP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('10', 'PacificPoker', 'P8')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('11', 'Partouche', 'PA')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('12', 'Merge', 'MN')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('13', 'PKR', 'PK')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('14', 'iPoker', 'IP')")
        # iPoker network variants
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('56', 'PMU Poker', 'IP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('57', 'FDJ Poker', 'IP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('58', 'Poker770', 'IP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('131', 'Betclic Poker', 'IP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('140', 'CoinPoker', 'CP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('59', 'NetBet Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('60', 'Barrière Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('61', 'Red Star Poker', 'IP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('62', 'Titan Poker', 'IP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('63', 'Bet365 Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('64', 'William Hill Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('65', 'Paddy Power Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('66', 'Betfair Poker', 'IP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('67', 'Coral Poker', 'IP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('68', 'Genting Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('69', 'Mansion Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('70', 'Winner Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('71', 'Ladbrokes Poker', 'IP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('72', 'Sky Poker', 'IP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('73', 'Sisal Poker', 'IP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('74', 'Lottomatica Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('75', 'Eurobet Poker', 'IP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('76', 'Snai Poker', 'IP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('77', 'Goldbet Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('78', 'Casino Barcelona Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('79', 'Sportium Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('80', 'Marca Apuestas Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('81', 'Everest Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('82', 'Bet-at-home Poker', 'IP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('83', 'Mybet Poker', 'IP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('84', 'Betsson Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('85', 'Betsafe Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('86', 'NordicBet Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('87', 'Unibet Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('88', 'Maria Casino Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('89', 'LeoVegas Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('90', 'Mr Green Poker', 'IP')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('91', 'Redbet Poker', 'IP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('15', 'Winamax', 'WM')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('16', 'Everest', 'EP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('17', 'Cake', 'CK')")
        # Cake network variants
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('92', 'Everygame Poker', 'CK')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('93', 'Everygame', 'CK')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('94', 'Cake Poker', 'CK')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('95', 'Juicy Stakes', 'CK')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('96', 'Juicy Stakes Poker', 'CK')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('97', 'JuicyStakes', 'CK')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('98', 'RedStar Poker', 'CK')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('99', 'RedStar', 'CK')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('100', 'Sportsbetting.ag Poker', 'CK')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('101', 'Sportsbetting Poker', 'CK')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('102', 'SportsBetting.ag', 'CK')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('18', 'Entraction', 'TR')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('19', 'BetOnline', 'BO')")
        # BetOnline network variants
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('103', 'BetOnline Poker', 'BO')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('104', 'BetOnline.ag', 'BO')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('105', 'Tiger Gaming', 'BO')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('106', 'TigerGaming', 'BO')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('107', 'Doyles Room', 'BO')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('108', 'DoylesRoom', 'BO')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('109', 'Poker4Ever', 'BO')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('110', 'Poker 4 Ever', 'BO')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('111', 'PlayersOnly', 'BO')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('112', 'Players Only', 'BO')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('113', 'SunPoker', 'BO')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('114', 'Sun Poker', 'BO')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('20', 'Microgaming', 'MG')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('21', 'Bovada', 'BV')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('22', 'Enet', 'EN')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('23', 'SealsWithClubs', 'SW')",
        )
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('24', 'WinningPoker', 'WP')",
        )
        # WPN network variants
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('115', 'Americas Cardroom', 'WP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('116', 'ACR Poker', 'WP')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('117', 'BlackChipPoker', 'WP')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('118', 'TruePoker', 'WP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('119', 'Ya Poker', 'WP')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('25', 'PokerMaster', 'PM')")
        c.execute(
            "INSERT INTO Sites (id,name,code) VALUES ('26', 'Run It Once Poker', 'RO')",
        )
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('27', 'GGPoker', 'GG')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('28', 'KingsClub', 'KC')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('29', 'PokerBros', 'PB')")
        c.execute("INSERT INTO Sites (id,name,code) VALUES ('30', 'Unibet', 'UN')")
        # c.execute("INSERT INTO Sites (id,name,code) VALUES ('31', 'PMU Poker', 'PM')")
        # Fill Actions
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('1', 'ante', 'A')")
        c.execute(
            "INSERT INTO Actions (id,name,code) VALUES ('2', 'small blind', 'SB')",
        )
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('3', 'secondsb', 'SSB')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('4', 'big blind', 'BB')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('5', 'both', 'SBBB')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('6', 'calls', 'C')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('7', 'raises', 'R')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('8', 'bets', 'B')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('9', 'stands pat', 'S')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('10', 'folds', 'F')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('11', 'checks', 'K')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('12', 'discards', 'D')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('13', 'bringin', 'I')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('14', 'completes', 'P')")
        c.execute("INSERT INTO Actions (id,name,code) VALUES ('15', 'straddle', 'ST')")
        c.execute(
            "INSERT INTO Actions (id,name,code) VALUES ('16', 'button blind', 'BUB')",
        )
        # Fill Rank. "Rank" is a reserved word since MySQL 8.0 (the RANK()
        # window function), so the MySQL catalogue creates the table as
        # `Rank` and these inserts must quote it the same way; PostgreSQL and
        # SQLite take the bare name.
        rank_table = "`Rank`" if self.backend == self.MYSQL_INNODB else "Rank"
        for rank_id, rank_name in (
            ("1", "Nothing"),
            ("2", "NoPair"),
            ("3", "OnePair"),
            ("4", "TwoPair"),
            ("5", "Trips"),
            ("6", "Straight"),
            ("7", "Flush"),
            ("8", "FlHouse"),
            ("9", "Quads"),
            ("10", "StFlush"),
        ):
            c.execute(f"INSERT INTO {rank_table} (id,name) VALUES ('{rank_id}', '{rank_name}')")  # nosec B608  # nosemgrep
        # Fill StartCards. `rank` is a reserved word since MySQL 8.0, so the
        # column is quoted in the MySQL catalogue; the inserts must quote it
        # too (same rule as the Rank table above).
        rank_col = "`rank`" if self.backend == self.MYSQL_INNODB else "rank"
        sql = f"INSERT INTO StartCards (category, name, {rank_col}, combinations) VALUES (%s, %s, %s, %s)".replace(  # nosec B608  # nosemgrep
            "%s",
            self.sql.query["placeholder"],
        )
        for i in range(170):
            (name, rank, combinations) = Card.StartCardRank(i)
            c.execute(sql, ("holdem", name, rank, combinations))
        for idx in range(-13, 1184):
            name = Card.decodeRazzStartHand(idx)
            c.execute(sql, ("razz", name, idx, 0))
        sql = f"INSERT INTO StartCards (id, category, name, {rank_col}, combinations) VALUES (%s, %s, %s, %s, %s)".replace(  # nosec B608  # nosemgrep
            "%s",
            self.sql.query["placeholder"],
        )
        omaha_count = len(Card._omaha_rank_combos()) * len(Card.OMAHA_SUIT_CLASSES)
        for idx in range(Card.OMAHA_START_HAND_OFFSET, Card.OMAHA_START_HAND_OFFSET + omaha_count):
            c.execute(sql, (idx, "omaha", Card.fourStartCardString(idx), idx, 0))

    # end def fillDefaultData
