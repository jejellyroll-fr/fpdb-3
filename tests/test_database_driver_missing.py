"""Test unit for missing database driver error handling."""

from unittest.mock import patch
import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Exceptions import FpdbDatabaseError


def test_postgresql_missing_driver_raises_fpdb_database_error():
    """Verify that _connect_postgresql raises FpdbDatabaseError when psycopg is missing."""
    db = Database.__new__(Database)
    db.host = "localhost"
    
    with patch.dict("sys.modules", {"psycopg": None}):
        with pytest.raises(FpdbDatabaseError) as exc_info:
            db._connect_postgresql("localhost", 5432, "fpdb", "fpdb", "fpdb")

    assert "PostgreSQL driver ('psycopg') is not installed" in str(exc_info.value)


def test_mysql_missing_driver_raises_fpdb_database_error():
    """Verify that _connect_mysql raises FpdbDatabaseError when MySQL drivers are missing."""
    db = Database.__new__(Database)
    db.host = "localhost"
    
    with patch.dict("sys.modules", {"MySQLdb": None, "pymysql": None}):
        with pytest.raises(FpdbDatabaseError) as exc_info:
            db._connect_mysql("localhost", 3306, "fpdb", "fpdb", "fpdb")

    assert "MySQL driver ('pymysql' / 'MySQLdb') is not installed" in str(exc_info.value)
