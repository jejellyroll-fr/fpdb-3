-- Migration: Add limp statistics columns
-- Tracking for street0Limp, street0OpenLimp, and street0OpenLimpChance persistence

-- MySQL - HandsPlayers table
ALTER TABLE HandsPlayers
    ADD COLUMN street0Limp BOOLEAN DEFAULT FALSE,
    ADD COLUMN street0OpenLimp BOOLEAN DEFAULT FALSE;

-- MySQL - HudCache table
ALTER TABLE HudCache
    ADD COLUMN street0Limp INT DEFAULT 0,
    ADD COLUMN street0OpenLimpChance INT DEFAULT 0,
    ADD COLUMN street0OpenLimp INT DEFAULT 0;

-- PostgreSQL - HandsPlayers table
-- ALTER TABLE HandsPlayers
--     ADD COLUMN street0Limp BOOLEAN DEFAULT FALSE,
--     ADD COLUMN street0OpenLimp BOOLEAN DEFAULT FALSE;

-- PostgreSQL - HudCache table
-- ALTER TABLE HudCache
--     ADD COLUMN street0Limp INT DEFAULT 0,
--     ADD COLUMN street0OpenLimpChance INT DEFAULT 0,
--     ADD COLUMN street0OpenLimp INT DEFAULT 0;

-- SQLite - HandsPlayers table (SQLite doesn't support ADD COLUMN with DEFAULT via ALTER TABLE directly)
-- For SQLite, columns are added dynamically when needed