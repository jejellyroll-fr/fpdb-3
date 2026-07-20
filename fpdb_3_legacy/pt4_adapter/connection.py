"""PT4 PostgreSQL connection utilities."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg


@dataclass
class Pt4Config:
    """Configuration for PT4 database connection."""

    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = "dbpass"
    database: str = "PT4 DB"  # PT4 default name with space

    @classmethod
    def from_env(cls) -> Pt4Config:
        """Load configuration from environment variables."""
        return cls(
            host=os.environ.get("PT4_HOST", "localhost"),
            port=int(os.environ.get("PT4_PORT", 5432)),
            user=os.environ.get("PT4_USER", "postgres"),
            password=os.environ.get("PT4_PASSWORD", "dbpass"),
            database=os.environ.get("PT4_DATABASE", "PT4 DB"),
        )


def connect_pt4(config: Pt4Config) -> psycopg.Connection:
    """Read-only connection to PT4 PostgreSQL database."""
    import psycopg  # deferred: only needed to actually connect, not to import the adapter

    return psycopg.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        dbname=config.database,
        autocommit=True,  # read-only, no transaction
    )
