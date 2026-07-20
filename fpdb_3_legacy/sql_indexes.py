"""Backend-specific SQL index catalogue."""

from __future__ import annotations


def index_queries(db_server: str) -> dict[str, str]:
    """Return index and indexed-column migration queries."""
    query: dict[str, str] = {}
    if db_server == "mysql":
        query["addTourneyIndex"] = (
            """ALTER TABLE Tourneys ADD UNIQUE INDEX siteTourneyNo(siteTourneyNo, tourneyTypeId)"""
        )
    elif db_server in ("postgresql", "sqlite"):
        query["addTourneyIndex"] = (
            """CREATE UNIQUE INDEX siteTourneyNo ON Tourneys (siteTourneyNo, tourneyTypeId)"""
        )

    if db_server == "mysql":
        query["addHandsIndex"] = (
            """ALTER TABLE Hands ADD UNIQUE INDEX siteHandNo(siteHandNo, gametypeId<heroseat>)"""
        )
    elif db_server in ("postgresql", "sqlite"):
        query["addHandsIndex"] = (
            """CREATE UNIQUE INDEX siteHandNo ON Hands (siteHandNo, gametypeId<heroseat>)"""
        )

    if db_server == "mysql":
        query["addPlayersSeat"] = (
            """ALTER TABLE HandsPlayers ADD UNIQUE INDEX playerSeat_idx(handId, seatNo)"""
        )
    elif db_server in ("postgresql", "sqlite"):
        query["addPlayersSeat"] = """CREATE UNIQUE INDEX playerSeat_idx ON HandsPlayers (handId, seatNo)"""

    if db_server == "mysql":
        query["addHeroSeat"] = """ALTER TABLE Hands ADD UNIQUE INDEX heroSeat_idx(id, heroSeat)"""
    elif db_server in ("postgresql", "sqlite"):
        query["addHeroSeat"] = """CREATE UNIQUE INDEX heroSeat_idx ON Hands (id, heroSeat)"""

    if db_server == "mysql":
        query["addHandsPlayersSeat"] = (
            """ALTER TABLE HandsPlayers ADD UNIQUE INDEX handsPlayerSeat_idx(handId, seatNo)"""
        )
    elif db_server in ("postgresql", "sqlite"):
        query["addHandsPlayersSeat"] = """CREATE UNIQUE INDEX handsPlayerSeat_idx ON Hands (handId, seatNo)"""

    if db_server == "mysql":
        query["addPlayersIndex"] = """ALTER TABLE Players ADD UNIQUE INDEX name(name, siteId)"""
    elif db_server in ("postgresql", "sqlite"):
        query["addPlayersIndex"] = """CREATE UNIQUE INDEX name ON Players (name, siteId)"""

    if db_server == "mysql":
        query["addTPlayersIndex"] = (
            """ALTER TABLE TourneysPlayers ADD UNIQUE INDEX _tourneyId(tourneyId, playerId, entryId)"""
        )
    elif db_server in ("postgresql", "sqlite"):
        query["addTPlayersIndex"] = (
            """CREATE UNIQUE INDEX tourneyId ON TourneysPlayers (tourneyId, playerId, entryId)"""
        )

    if db_server == "mysql":
        query["addStartCardsIndex"] = """ALTER TABLE StartCards ADD UNIQUE INDEX cards_idx (category, `rank`)"""
    elif db_server in ("postgresql", "sqlite"):
        query["addStartCardsIndex"] = """CREATE UNIQUE INDEX cards_idx ON StartCards (category, rank)"""

    if db_server == "mysql":
        query["addSeatsIndex"] = """ALTER TABLE Hands ADD INDEX seats_idx (seats)"""
    elif db_server in ("postgresql", "sqlite"):
        query["addSeatsIndex"] = """CREATE INDEX seats_idx ON Hands (seats)"""

    if db_server == "mysql":
        query["addPositionIndex"] = """ALTER TABLE HandsPlayers ADD INDEX position_idx (position)"""
    elif db_server in ("postgresql", "sqlite"):
        query["addPositionIndex"] = """CREATE INDEX position_idx ON HandsPlayers (position)"""

    if db_server == "mysql":
        query["addPlayerAutoNotesPlayerIndex"] = (
            """ALTER TABLE PlayerAutoNotes ADD INDEX playerautonotes_player_idx (playerId)"""
        )
        query["addPlayerAutoNotesHandIndex"] = (
            """ALTER TABLE PlayerAutoNotes ADD INDEX playerautonotes_hand_idx (handId)"""
        )
        query["addPlayerAutoNotesRuleIndex"] = (
            """ALTER TABLE PlayerAutoNotes ADD INDEX playerautonotes_rule_idx (ruleId, ruleVersion)"""
        )
    elif db_server in ("postgresql", "sqlite"):
        query["addPlayerAutoNotesPlayerIndex"] = (
            """CREATE INDEX playerautonotes_player_idx ON PlayerAutoNotes (playerId)"""
        )
        query["addPlayerAutoNotesHandIndex"] = (
            """CREATE INDEX playerautonotes_hand_idx ON PlayerAutoNotes (handId)"""
        )
        query["addPlayerAutoNotesRuleIndex"] = (
            """CREATE INDEX playerautonotes_rule_idx ON PlayerAutoNotes (ruleId, ruleVersion)"""
        )

    if db_server == "mysql":
        query["addStartCashIndex"] = """ALTER TABLE HandsPlayers ADD INDEX cash_idx (startCash)"""
    elif db_server in ("postgresql", "sqlite"):
        query["addStartCashIndex"] = """CREATE INDEX cash_idx ON HandsPlayers (startCash)"""

    if db_server == "mysql":
        query["addEffStackIndex"] = """ALTER TABLE HandsPlayers ADD INDEX eff_stack_idx (effStack)"""
    elif db_server in ("postgresql", "sqlite"):
        query["addEffStackIndex"] = """CREATE INDEX eff_stack_idx ON HandsPlayers (effStack)"""

    if db_server == "mysql":
        query["addTotalProfitIndex"] = """ALTER TABLE HandsPlayers ADD INDEX profit_idx (totalProfit)"""
    elif db_server in ("postgresql", "sqlite"):
        query["addTotalProfitIndex"] = """CREATE INDEX profit_idx ON HandsPlayers (totalProfit)"""

    if db_server == "mysql":
        query["addWinningsIndex"] = """ALTER TABLE HandsPlayers ADD INDEX winnings_idx (winnings)"""
    elif db_server in ("postgresql", "sqlite"):
        query["addWinningsIndex"] = """CREATE INDEX winnings_idx ON HandsPlayers (winnings)"""

    if db_server == "mysql":
        query["addFinalPotIndex"] = """ALTER TABLE Hands ADD INDEX pot_idx (finalPot)"""
    elif db_server in ("postgresql", "sqlite"):
        query["addFinalPotIndex"] = """CREATE INDEX pot_idx ON Hands (finalPot)"""
    # Add bombPot column to existing Hands tables
    if db_server in {"mysql", "postgresql"}:
        query["addBombPotColumn"] = """ALTER TABLE Hands ADD COLUMN bombPot BIGINT DEFAULT 0"""
    elif db_server == "sqlite":
        query["addBombPotColumn"] = """ALTER TABLE Hands ADD COLUMN bombPot INT DEFAULT 0"""
    # Add index for bombPot queries
    if db_server == "mysql":
        query["addBombPotIndex"] = """ALTER TABLE Hands ADD INDEX bomb_pot_idx (bombPot)"""
    elif db_server in ("postgresql", "sqlite"):
        query["addBombPotIndex"] = """CREATE INDEX bomb_pot_idx ON Hands (bombPot)"""
    # Add splashPot column to existing Hands tables
    if db_server in {"mysql", "postgresql"}:
        query["addSplashPotColumn"] = """ALTER TABLE Hands ADD COLUMN splashPot BIGINT DEFAULT 0"""
    elif db_server == "sqlite":
        query["addSplashPotColumn"] = """ALTER TABLE Hands ADD COLUMN splashPot INT DEFAULT 0"""
    # Add index for splashPot queries
    if db_server == "mysql":
        query["addSplashPotIndex"] = """ALTER TABLE Hands ADD INDEX splash_pot_idx (splashPot)"""
    elif db_server in ("postgresql", "sqlite"):
        query["addSplashPotIndex"] = """CREATE INDEX splash_pot_idx ON Hands (splashPot)"""

    if db_server == "mysql":
        query["addStreetIndex"] = """ALTER TABLE HandsStove ADD INDEX street_idx (streetId, boardId)"""
    elif db_server in ("postgresql", "sqlite"):
        query["addStreetIndex"] = """CREATE INDEX street_idx ON HandsStove (streetId, boardId)"""

    query["addSessionsCacheCompundIndex"] = (
        """CREATE INDEX SessionsCache_Compound_idx ON SessionsCache(gametypeId, playerId)"""
    )
    query["addTourneysCacheCompundIndex"] = (
        """CREATE UNIQUE INDEX TourneysCache_Compound_idx ON TourneysCache(tourneyId, playerId)"""
    )
    query["addHudCacheCompundIndex"] = (
        """CREATE UNIQUE INDEX HudCache_Compound_idx ON HudCache(gametypeId, playerId, seats, position, tourneyTypeId, styleKey)"""
    )

    query["addCardsCacheCompundIndex"] = (
        """CREATE UNIQUE INDEX CardsCache_Compound_idx ON CardsCache(weekId, monthId, gametypeId, tourneyTypeId, playerId, startCards)"""
    )
    query["addPositionsCacheCompundIndex"] = (
        """CREATE UNIQUE INDEX PositionsCache_Compound_idx ON PositionsCache(weekId, monthId, gametypeId, tourneyTypeId, playerId, seats, maxPosition, position)"""
    )

    # (left(file, 255)) is not valid syntax on postgres psycopg on windows (postgres v8.4)
    # error thrown is HINT:  "No function matches the given name and argument types. You might need to add explicit type casts."
    # so we will just create the index with the full filename.
    if db_server == "mysql":
        query["addFilesIndex"] = """CREATE UNIQUE INDEX index_file ON Files (file(255))"""
    elif db_server in ("postgresql", "sqlite"):
        query["addFilesIndex"] = """CREATE UNIQUE INDEX index_file ON Files (file)"""

    query["addTableNameIndex"] = """CREATE INDEX index_tableName ON Hands (tableName)"""
    query["addPlayerNameIndex"] = """CREATE INDEX index_playerName ON Players (name)"""
    query["addPlayerHeroesIndex"] = """CREATE INDEX player_heroes ON Players (hero)"""

    return query
