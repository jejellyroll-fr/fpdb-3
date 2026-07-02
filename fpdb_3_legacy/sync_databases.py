#!/usr/bin/env python3
from __future__ import annotations
"""Synchronize data from legacy database to modern database

This script syncs new hands and players from the legacy database (desktop app)
to the modern database (web app).

Usage:
    # One-time sync
    python sync_databases.py

    # Watch mode - auto-sync when changes detected
    python sync_databases.py --watch

    # Force full re-sync
    python sync_databases.py --force
"""

import argparse
import logging
import time
from pathlib import Path
from datetime import datetime

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from fpdb.infrastructure.database.models.legacy_models import (
    LegacyBase,
    LegacyHandModel,
    LegacyPlayerModel,
)
from fpdb.infrastructure.database.models.hand_model import HandModel
from fpdb.infrastructure.database.models.player_model import PlayerModel
from fpdb.infrastructure.adapters.legacy_schema_adapter import LegacySchemaAdapter
from fpdb.infrastructure.repositories.hand_repository_impl import HandRepositoryImpl
from fpdb.infrastructure.repositories.player_repository_impl import PlayerRepositoryImpl

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# Colors for terminal output
class Colors:
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


class DatabaseSyncer:
    """Synchronizes data from legacy to modern database"""

    def __init__(self, legacy_db_path: Path, modern_db_path: Path):
        """Initialize syncer

        Args:
            legacy_db_path: Path to legacy database
            modern_db_path: Path to modern database
        """
        self.legacy_db_path = legacy_db_path
        self.modern_db_path = modern_db_path
        self.adapter = LegacySchemaAdapter()

        # Create sessions
        self._init_sessions()

    def _init_sessions(self):
        """Initialize database sessions"""
        # Legacy database (read-only)
        legacy_url = f"sqlite:///{self.legacy_db_path}"
        self.legacy_engine = create_engine(legacy_url, echo=False)
        LegacySession = sessionmaker(bind=self.legacy_engine)
        self.legacy_session = LegacySession()

        # Modern database (read-write)
        modern_url = f"sqlite:///{self.modern_db_path}"
        self.modern_engine = create_engine(modern_url, echo=False)
        ModernSession = sessionmaker(bind=self.modern_engine)
        self.modern_session = ModernSession()

    def get_counts(self):
        """Get counts from both databases

        Returns:
            Tuple of (legacy_players, modern_players, legacy_hands, modern_hands)
        """
        legacy_players = self.legacy_session.query(func.count(LegacyPlayerModel.id)).scalar()
        legacy_hands = self.legacy_session.query(func.count(LegacyHandModel.id)).scalar()

        modern_players = self.modern_session.query(func.count(PlayerModel.id)).scalar()
        modern_hands = self.modern_session.query(func.count(HandModel.id)).scalar()

        return legacy_players, modern_players, legacy_hands, modern_hands

    def sync_players(self) -> int:
        """Sync new players from legacy to modern

        Returns:
            Number of new players synced
        """
        # Get existing player names in modern DB
        existing_names = {name for (name,) in self.modern_session.query(PlayerModel.name).all()}

        # Get all players from legacy DB
        legacy_players = self.legacy_session.query(LegacyPlayerModel).all()

        new_count = 0
        for legacy_player in legacy_players:
            if legacy_player.name not in existing_names:
                # Convert and save new player
                player_entity = self.adapter.to_player_entity(legacy_player)
                player_model = PlayerModel.from_entity(player_entity)
                self.modern_session.add(player_model)
                new_count += 1

        if new_count > 0:
            self.modern_session.commit()
            logger.info(f"{Colors.OKGREEN}✓ Synced {new_count} new players{Colors.ENDC}")

        return new_count

    def sync_hands(self) -> int:
        """Sync new hands from legacy to modern

        Returns:
            Number of new hands synced
        """
        # Get existing site hand IDs in modern DB
        existing_site_hand_ids = {
            site_hand_id for (site_hand_id,) in self.modern_session.query(HandModel.site_hand_id).all()
        }

        # Get all hands from legacy DB
        legacy_hands = (
            self.legacy_session.query(LegacyHandModel).join(LegacyHandModel.gametype).join(LegacyHandModel.site).all()
        )

        new_count = 0
        for legacy_hand in legacy_hands:
            if legacy_hand.siteHandNo not in existing_site_hand_ids:
                try:
                    # Convert and save new hand
                    hand_entity = self.adapter.to_hand_entity(legacy_hand)
                    hand_model = HandModel.from_entity(hand_entity)
                    self.modern_session.add(hand_model)
                    new_count += 1
                except Exception as e:
                    logger.warning(f"Failed to sync hand {legacy_hand.siteHandNo}: {e}")

        if new_count > 0:
            self.modern_session.commit()
            logger.info(f"{Colors.OKGREEN}✓ Synced {new_count} new hands{Colors.ENDC}")

        return new_count

    def sync(self, force: bool = False):
        """Perform synchronization

        Args:
            force: If True, force full re-sync
        """
        start_time = time.time()

        logger.info(f"{Colors.OKBLUE}Starting synchronization...{Colors.ENDC}")
        logger.info(f"  Legacy DB: {self.legacy_db_path}")
        logger.info(f"  Modern DB: {self.modern_db_path}")

        # Get current counts
        legacy_players, modern_players, legacy_hands, modern_hands = self.get_counts()

        logger.info(f"\n{Colors.OKCYAN}Current state:{Colors.ENDC}")
        logger.info(f"  Players: {modern_players}/{legacy_players} (modern/legacy)")
        logger.info(f"  Hands:   {modern_hands}/{legacy_hands} (modern/legacy)")

        # Check if sync needed
        if not force and modern_players >= legacy_players and modern_hands >= legacy_hands:
            logger.info(f"\n{Colors.OKGREEN}✓ Already in sync - no changes needed{Colors.ENDC}")
            return

        # Sync players
        logger.info(f"\n{Colors.OKBLUE}Syncing players...{Colors.ENDC}")
        new_players = self.sync_players()

        # Sync hands
        logger.info(f"{Colors.OKBLUE}Syncing hands...{Colors.ENDC}")
        new_hands = self.sync_hands()

        # Summary
        elapsed = time.time() - start_time
        logger.info(f"\n{Colors.BOLD}{Colors.OKGREEN}Sync completed in {elapsed:.2f}s{Colors.ENDC}")
        logger.info(f"  New players: {new_players}")
        logger.info(f"  New hands:   {new_hands}")

    def watch(self, interval: int = 10):
        """Watch for changes and auto-sync

        Args:
            interval: Check interval in seconds
        """
        logger.info(f"\n{Colors.BOLD}{Colors.OKCYAN}Starting watch mode...{Colors.ENDC}")
        logger.info(f"Checking for changes every {interval} seconds")
        logger.info(f"{Colors.WARNING}Press Ctrl+C to stop{Colors.ENDC}\n")

        last_counts = self.get_counts()

        try:
            while True:
                time.sleep(interval)

                current_counts = self.get_counts()

                # Check if legacy database has changed
                if current_counts != last_counts:
                    logger.info(f"\n{Colors.WARNING}Changes detected!{Colors.ENDC}")
                    self.sync()
                    last_counts = current_counts
                else:
                    # Show heartbeat
                    print(".", end="", flush=True)

        except KeyboardInterrupt:
            logger.info(f"\n\n{Colors.WARNING}Stopping watch mode{Colors.ENDC}")

    def close(self):
        """Close database connections"""
        self.legacy_session.close()
        self.modern_session.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Sync data from legacy to modern database", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--legacy-db",
        type=Path,
        default=Path.home() / ".fpdb" / "database" / "fpdb.db3",
        help="Path to legacy database (default: ~/.fpdb/database/fpdb.db3)",
    )
    parser.add_argument(
        "--modern-db",
        type=Path,
        default=Path.home() / ".fpdb" / "fpdb.db",
        help="Path to modern database (default: ~/.fpdb/fpdb.db)",
    )
    parser.add_argument("--watch", action="store_true", help="Watch mode - auto-sync when changes detected")
    parser.add_argument("--interval", type=int, default=10, help="Check interval in watch mode (seconds, default: 10)")
    parser.add_argument("--force", action="store_true", help="Force full re-sync")

    args = parser.parse_args()

    # Check if legacy database exists
    if not args.legacy_db.exists():
        logger.error(f"{Colors.FAIL}Legacy database not found: {args.legacy_db}{Colors.ENDC}")
        return

    # Create syncer
    syncer = DatabaseSyncer(
        legacy_db_path=args.legacy_db,
        modern_db_path=args.modern_db,
    )

    try:
        if args.watch:
            syncer.watch(interval=args.interval)
        else:
            syncer.sync(force=args.force)
    finally:
        syncer.close()


if __name__ == "__main__":
    main()
