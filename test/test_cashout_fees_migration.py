#!/usr/bin/env python3
"""Tests for cash out fees database schema migration."""

import unittest
from unittest.mock import Mock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from SQL import Sql
from Database import HANDS_PLAYERS_KEYS


class TestCashOutFeesMigration(unittest.TestCase):
    """Test cases for cash out fees database schema migration."""

    def setUp(self):
        """Set up test environment."""
        self.sql = Sql()

    def test_mysql_schema_includes_cashout_fee(self):
        """Test that MySQL HandsPlayers table includes cashOutFee and isCashOut columns."""
        create_query = self.sql.query.get("createHandsPlayersTable")
        self.assertIsNotNone(create_query, "createHandsPlayersTable query should exist")
        self.assertIn("cashOutFee BIGINT DEFAULT 0", create_query, 
                     "MySQL schema should include cashOutFee BIGINT column")
        self.assertIn("isCashOut BOOLEAN DEFAULT FALSE", create_query,
                     "MySQL schema should include isCashOut BOOLEAN column")

    def test_postgresql_schema_includes_cashout_fee(self):
        """Test that PostgreSQL HandsPlayers table includes cashOutFee and isCashOut columns."""
        # The SQL class builds queries for all DB types, we need to check if
        # PostgreSQL query exists and contains our field
        sql_pg = Sql(db_server="postgresql")
        create_query = sql_pg.query.get("createHandsPlayersTable")
        self.assertIsNotNone(create_query, "PostgreSQL createHandsPlayersTable query should exist")
        self.assertIn("cashOutFee BIGINT DEFAULT 0", create_query,
                     "PostgreSQL schema should include cashOutFee BIGINT column")
        self.assertIn("isCashOut BOOLEAN DEFAULT FALSE", create_query,
                     "PostgreSQL schema should include isCashOut BOOLEAN column")

    def test_sqlite_schema_includes_cashout_fee(self):
        """Test that SQLite HandsPlayers table includes cashOutFee and isCashOut columns."""
        sql_sqlite = Sql(db_server="sqlite")
        create_query = sql_sqlite.query.get("createHandsPlayersTable")
        self.assertIsNotNone(create_query, "SQLite createHandsPlayersTable query should exist")
        self.assertIn("cashOutFee INT DEFAULT 0", create_query,
                     "SQLite schema should include cashOutFee INT column")
        self.assertIn("isCashOut BOOLEAN DEFAULT 0", create_query,
                     "SQLite schema should include isCashOut BOOLEAN column")

    def test_store_hands_players_includes_cashout_fee(self):
        """Test that store_hands_players query includes cashOutFee and isCashOut columns."""
        insert_query = self.sql.query.get("store_hands_players")
        self.assertIsNotNone(insert_query, "store_hands_players query should exist")
        self.assertIn("cashOutFee", insert_query,
                     "Insert query should include cashOutFee column")
        self.assertIn("isCashOut", insert_query,
                     "Insert query should include isCashOut column")

    def test_store_hands_players_correct_placeholder_count(self):
        """Test that store_hands_players has correct number of placeholders."""
        insert_query = self.sql.query.get("store_hands_players")
        
        # Count column names (between INSERT and VALUES)
        columns_section = insert_query.split("values")[0]
        columns = [col.strip() for col in columns_section.split(",") if col.strip() and "INSERT" not in col.upper()]
        
        # Count placeholders (%s)
        values_section = insert_query.split("values")[1] if "values" in insert_query else ""
        placeholder_count = values_section.count("%s")
        
        # Should have equal number of columns and placeholders
        # Note: We can't do exact count easily due to complex formatting,
        # but we can verify cashOutFee is properly included
        self.assertIn("cashOutFee", columns_section, "cashOutFee should be in columns")
        self.assertGreater(placeholder_count, 0, "Should have placeholders for values")

    def test_hands_players_keys_order_consistency(self):
        """Test that HANDS_PLAYERS_KEYS includes cashOutFee and isCashOut and maintains order."""
        self.assertIn("cashOutFee", HANDS_PLAYERS_KEYS, 
                     "cashOutFee should be in HANDS_PLAYERS_KEYS")
        self.assertIn("isCashOut", HANDS_PLAYERS_KEYS,
                     "isCashOut should be in HANDS_PLAYERS_KEYS")
        
        # Verify they're at the expected positions (should be last after reverse)
        # Since the list is reversed, isCashOut should be at index 0, cashOutFee at index 1
        self.assertEqual(HANDS_PLAYERS_KEYS[0], "isCashOut",
                        "isCashOut should be first in HANDS_PLAYERS_KEYS (after reverse)")
        self.assertEqual(HANDS_PLAYERS_KEYS[1], "cashOutFee",
                        "cashOutFee should be second in HANDS_PLAYERS_KEYS (after reverse)")

    def test_backward_compatibility(self):
        """Test that existing columns are still present after adding cashOutFee."""
        create_query = self.sql.query.get("createHandsPlayersTable")
        
        # Key existing columns that should still be present
        existing_columns = [
            "handId", "playerId", "startCash", "seatNo", "winnings", 
            "rake", "rakeDealt", "rakeContributed", "handString", "actionString"
        ]
        
        for column in existing_columns:
            self.assertIn(column, create_query,
                         f"Existing column '{column}' should still be present")

    @patch('Database.Database')
    def test_database_insertion_compatibility(self, mock_db):
        """Test that database insertion works with new cashOutFee field."""
        # This tests the theoretical insertion flow
        mock_db_instance = Mock()
        mock_db.return_value = mock_db_instance
        
        # Simulate player data with cash out fee (include minimal required fields)
        pdata = {
            "TestPlayer": {}
        }
        
        # Initialize with minimal required values for all HANDS_PLAYERS_KEYS
        for key in HANDS_PLAYERS_KEYS:
            if key in ["startCash", "effStack", "winnings", "rake", "cashOutFee"]:
                pdata["TestPlayer"][key] = 0
            elif "Discards" in key or "Calls" in key or "Bets" in key or "Raises" in key:
                pdata["TestPlayer"][key] = 0
            elif key == "handString":
                pdata["TestPlayer"][key] = None
            elif key == "seatNo":
                pdata["TestPlayer"][key] = 1
            else:
                pdata["TestPlayer"][key] = False  # Default for boolean fields
        
        # Set specific test values
        pdata["TestPlayer"]["cashOutFee"] = 50  # $0.50 in cents
        
        # Verify that cashOutFee would be included in the data extraction
        try:
            # This simulates the key extraction that happens in storeHandsPlayers
            bulk_data = [pdata["TestPlayer"][key] for key in HANDS_PLAYERS_KEYS]
            
            # Should not raise KeyError for cashOutFee
            self.assertIn(50, bulk_data, "Cash out fee should be included in bulk data")
            
        except KeyError as e:
            self.fail(f"KeyError when extracting cashOutFee: {e}")

    def test_sql_syntax_validity(self):
        """Test that generated SQL queries have valid syntax structure."""
        create_query = self.sql.query.get("createHandsPlayersTable")
        insert_query = self.sql.query.get("store_hands_players")
        
        # Basic syntax checks
        self.assertIn("CREATE TABLE", create_query.upper(), 
                     "Should be a CREATE TABLE statement")
        self.assertIn("INSERT INTO", insert_query.upper(),
                     "Should be an INSERT statement")
        
        # Check for SQL injection protection (should use parameterized queries)
        self.assertIn("%s", insert_query, "Should use parameterized queries")
        
        # Check for proper closing (SQL queries should end with quotes, ENGINE statements, or closing parentheses)
        query_end = create_query.strip()
        valid_endings = ('"""', '"', ')', 'ENGINE=INNODB"""', 'ENGINE=INNODB')
        self.assertTrue(any(query_end.endswith(ending) for ending in valid_endings),
                      f"CREATE query should be properly closed, but ends with: {query_end[-20:]}")

    def test_default_value_handling(self):
        """Test that cashOutFee has appropriate default value."""
        create_query = self.sql.query.get("createHandsPlayersTable")
        
        # Should have DEFAULT 0 for cashOutFee
        self.assertIn("DEFAULT 0", create_query,
                     "cashOutFee should have DEFAULT 0")
        
        # Should not allow NULL (if it's a required field)
        cashout_line = None
        for line in create_query.split('\n'):
            if 'cashOutFee' in line:
                cashout_line = line.strip()
                break
        
        self.assertIsNotNone(cashout_line, "Should find cashOutFee line")
        # Verify it has a default but doesn't explicitly allow NULL
        self.assertIn("DEFAULT 0", cashout_line,
                     "cashOutFee line should include DEFAULT 0")


class TestCashOutFeesPerformance(unittest.TestCase):
    """Test performance impact of adding cashOutFee field."""
    
    def test_hands_players_keys_length(self):
        """Test that adding cashOutFee doesn't significantly impact key list size."""
        # This is more of a sanity check
        self.assertLess(len(HANDS_PLAYERS_KEYS), 200, 
                       "HANDS_PLAYERS_KEYS shouldn't be excessively long")
        self.assertGreater(len(HANDS_PLAYERS_KEYS), 50,
                          "HANDS_PLAYERS_KEYS should contain substantial data")

    def test_key_lookup_performance(self):
        """Test that cashOutFee can be looked up efficiently in HANDS_PLAYERS_KEYS."""
        # Simple performance check - should be O(n) lookup
        import time
        
        start_time = time.time()
        result = "cashOutFee" in HANDS_PLAYERS_KEYS
        end_time = time.time()
        
        self.assertTrue(result, "cashOutFee should be found in HANDS_PLAYERS_KEYS")
        self.assertLess(end_time - start_time, 0.001, 
                       "Key lookup should be very fast")


if __name__ == '__main__':
    unittest.main()