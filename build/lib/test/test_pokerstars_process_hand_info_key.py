"""Tests for PokerStarsToFpdb._processHandInfoKey method and its helper functions."""

import unittest
from unittest.mock import Mock, patch

from PokerStarsToFpdb import PokerStars


class MockConfig:
    """Mock configuration for testing."""

    def get_import_parameters(self) -> dict:
        """Return import parameters for testing."""
        return {
            "saveActions": True,
            "callFpdbHud": False,
            "cacheSessions": False,
            "publicDB": False,
            "importFilters": [
                "holdem",
                "omahahi",
                "omahahilo",
                "studhi",
                "studlo",
                "razz",
                "27_1draw",
                "27_3draw",
                "fivedraw",
                "badugi",
                "baduci",
            ],
            "handCount": 0,
            "fastFold": False,
        }

    def get_site_id(self, sitename: str) -> int:
        """Return the site ID for the given site name."""
        return 32  # PokerStars.COM


class TestProcessHandInfoKey(unittest.TestCase):
    """Test _processHandInfoKey method and its helper functions."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.config = MockConfig()
        self.parser = PokerStars(self.config)
        self.mock_hand = Mock()
        self.mock_hand.handid = None
        self.mock_hand.tourNo = None
        self.mock_hand.level = None
        self.mock_hand.isShootout = False
        self.mock_hand.buttonpos = None
        self.mock_hand.maxseats = None
        self.mock_hand.tablename = None

    def test_process_basic_hand_fields_datetime(self) -> None:
        """Test processing DATETIME field."""
        info = {"DATETIME": "2024/01/01 12:00:00 ET"}

        with patch.object(self.parser, "_processDateTime") as mock_process_datetime:
            self.parser._processHandInfoKey("DATETIME", info, self.mock_hand)
            mock_process_datetime.assert_called_once_with("2024/01/01 12:00:00 ET", self.mock_hand)

    def test_process_basic_hand_fields_hid(self) -> None:
        """Test processing HID field."""
        info = {"HID": "123456789"}

        self.parser._processHandInfoKey("HID", info, self.mock_hand)
        self.assertEqual(self.mock_hand.handid, "123456789")

    def test_process_basic_hand_fields_tourno(self) -> None:
        """Test processing TOURNO field."""
        info = {"TOURNO": "987654321123456789"}  # 18 character tournament number

        self.parser._processHandInfoKey("TOURNO", info, self.mock_hand)
        self.assertEqual(self.mock_hand.tourNo, "987654321123456789")  # All 18 chars

    def test_process_basic_hand_fields_tourno_none(self) -> None:
        """Test processing TOURNO field when None."""
        info = {"TOURNO": None}

        self.parser._processHandInfoKey("TOURNO", info, self.mock_hand)
        self.assertIsNone(self.mock_hand.tourNo)

    def test_process_basic_hand_fields_tourno_truncation(self) -> None:
        """Test processing TOURNO field truncates to last 18 chars when longer."""
        info = {"TOURNO": "123456789012345678901234567890"}  # 30 chars

        self.parser._processHandInfoKey("TOURNO", info, self.mock_hand)
        self.assertEqual(self.mock_hand.tourNo, "345678901234567890")  # Last 18 chars

    def test_process_tournament_fields_buyin_with_tourno(self) -> None:
        """Test processing BUYIN field when tournament number exists."""
        self.mock_hand.tourNo = "123456789"
        info = {"BUYIN": "$5.50+$0.50"}

        with patch.object(self.parser, "_processBuyinInfo") as mock_process_buyin:
            self.parser._processHandInfoKey("BUYIN", info, self.mock_hand)
            mock_process_buyin.assert_called_once_with(info, self.mock_hand)

    def test_process_tournament_fields_buyin_no_tourno(self) -> None:
        """Test processing BUYIN field when no tournament number."""
        self.mock_hand.tourNo = None
        info = {"BUYIN": "$5.50+$0.50"}

        with patch.object(self.parser, "_processBuyinInfo") as mock_process_buyin:
            self.parser._processHandInfoKey("BUYIN", info, self.mock_hand)
            mock_process_buyin.assert_not_called()

    def test_process_tournament_fields_level(self) -> None:
        """Test processing LEVEL field."""
        info = {"LEVEL": "I"}

        self.parser._processHandInfoKey("LEVEL", info, self.mock_hand)
        self.assertEqual(self.mock_hand.level, "I")

    def test_process_tournament_fields_shootout(self) -> None:
        """Test processing SHOOTOUT field."""
        info = {"SHOOTOUT": True}

        self.parser._processHandInfoKey("SHOOTOUT", info, self.mock_hand)
        self.assertTrue(self.mock_hand.isShootout)

    def test_process_tournament_fields_shootout_none(self) -> None:
        """Test processing SHOOTOUT field when None."""
        info = {"SHOOTOUT": None}

        self.parser._processHandInfoKey("SHOOTOUT", info, self.mock_hand)
        self.assertFalse(self.mock_hand.isShootout)

    def test_process_table_fields_table(self) -> None:
        """Test processing TABLE field."""
        info = {"TABLE": "Badugi II"}

        with patch.object(self.parser, "_processTableInfo") as mock_process_table:
            self.parser._processHandInfoKey("TABLE", info, self.mock_hand)
            mock_process_table.assert_called_once_with(info, self.mock_hand)

    def test_process_table_fields_button(self) -> None:
        """Test processing BUTTON field."""
        info = {"BUTTON": 3}

        self.parser._processHandInfoKey("BUTTON", info, self.mock_hand)
        self.assertEqual(self.mock_hand.buttonpos, 3)

    def test_process_table_fields_max(self) -> None:
        """Test processing MAX field."""
        info = {"MAX": "6"}

        self.parser._processHandInfoKey("MAX", info, self.mock_hand)
        self.assertEqual(self.mock_hand.maxseats, 6)

    def test_process_table_fields_max_none(self) -> None:
        """Test processing MAX field when None."""
        info = {"MAX": None}

        self.parser._processHandInfoKey("MAX", info, self.mock_hand)
        self.assertIsNone(self.mock_hand.maxseats)

    def test_process_unknown_key(self) -> None:
        """Test processing unknown key does nothing."""
        info = {"UNKNOWN_KEY": "some_value"}
        original_handid = self.mock_hand.handid

        self.parser._processHandInfoKey("UNKNOWN_KEY", info, self.mock_hand)
        self.assertEqual(self.mock_hand.handid, original_handid)


class TestProcessHandInfoKeyHelperMethods(unittest.TestCase):
    """Test the helper methods called by _processHandInfoKey."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.config = MockConfig()
        self.parser = PokerStars(self.config)
        self.mock_hand = Mock()
        self.mock_hand.handid = None
        self.mock_hand.tourNo = None
        self.mock_hand.level = None
        self.mock_hand.isShootout = False
        self.mock_hand.buttonpos = None
        self.mock_hand.maxseats = None
        self.mock_hand.tablename = None

    def test_process_basic_hand_fields_datetime_call(self) -> None:
        """Test _processBasicHandFields calls _processDateTime for DATETIME."""
        info = {"DATETIME": "2024/01/01 12:00:00 ET"}

        with patch.object(self.parser, "_processDateTime") as mock_process_datetime:
            self.parser._processBasicHandFields("DATETIME", info, self.mock_hand)
            mock_process_datetime.assert_called_once_with("2024/01/01 12:00:00 ET", self.mock_hand)

    def test_process_basic_hand_fields_hid_assignment(self) -> None:
        """Test _processBasicHandFields assigns HID to hand.handid."""
        info = {"HID": "987654321"}

        self.parser._processBasicHandFields("HID", info, self.mock_hand)
        self.assertEqual(self.mock_hand.handid, "987654321")

    def test_process_basic_hand_fields_tourno_truncation(self) -> None:
        """Test _processBasicHandFields truncates TOURNO to last 18 chars."""
        info = {"TOURNO": "123456789012345678901234567890"}  # 30 chars

        self.parser._processBasicHandFields("TOURNO", info, self.mock_hand)
        self.assertEqual(self.mock_hand.tourNo, "345678901234567890")  # Last 18

    def test_process_tournament_fields_buyin_conditional(self) -> None:
        """Test _processTournamentFields only processes BUYIN when tourNo exists."""
        # Test with tourNo
        self.mock_hand.tourNo = "123456789"
        info = {"BUYIN": "$10+$1"}

        with patch.object(self.parser, "_processBuyinInfo") as mock_process_buyin:
            self.parser._processTournamentFields("BUYIN", info, self.mock_hand)
            mock_process_buyin.assert_called_once_with(info, self.mock_hand)

        # Test without tourNo
        self.mock_hand.tourNo = None
        mock_process_buyin.reset_mock()

        self.parser._processTournamentFields("BUYIN", info, self.mock_hand)
        mock_process_buyin.assert_not_called()

    def test_process_tournament_fields_level_assignment(self) -> None:
        """Test _processTournamentFields assigns LEVEL to hand.level."""
        info = {"LEVEL": "XII"}

        self.parser._processTournamentFields("LEVEL", info, self.mock_hand)
        self.assertEqual(self.mock_hand.level, "XII")

    def test_process_tournament_fields_shootout_flag(self) -> None:
        """Test _processTournamentFields sets isShootout flag when SHOOTOUT is not None."""
        info = {"SHOOTOUT": "Yes"}

        self.parser._processTournamentFields("SHOOTOUT", info, self.mock_hand)
        self.assertTrue(self.mock_hand.isShootout)

        # Test with None value
        info = {"SHOOTOUT": None}
        self.mock_hand.isShootout = False

        self.parser._processTournamentFields("SHOOTOUT", info, self.mock_hand)
        self.assertFalse(self.mock_hand.isShootout)

    def test_process_table_fields_table_info_call(self) -> None:
        """Test _processTableFields calls _processTableInfo for TABLE."""
        info = {"TABLE": "Test Table 123"}

        with patch.object(self.parser, "_processTableInfo") as mock_process_table:
            self.parser._processTableFields("TABLE", info, self.mock_hand)
            mock_process_table.assert_called_once_with(info, self.mock_hand)

    def test_process_table_fields_button_assignment(self) -> None:
        """Test _processTableFields assigns BUTTON to hand.buttonpos."""
        info = {"BUTTON": 5}

        self.parser._processTableFields("BUTTON", info, self.mock_hand)
        self.assertEqual(self.mock_hand.buttonpos, 5)

    def test_process_table_fields_max_conversion(self) -> None:
        """Test _processTableFields converts MAX to int and assigns to maxseats."""
        info = {"MAX": "9"}

        self.parser._processTableFields("MAX", info, self.mock_hand)
        self.assertEqual(self.mock_hand.maxseats, 9)

        # Test with None value
        info = {"MAX": None}
        self.mock_hand.maxseats = None

        self.parser._processTableFields("MAX", info, self.mock_hand)
        self.assertIsNone(self.mock_hand.maxseats)

    def test_process_table_info_tournament_with_hivetable(self) -> None:
        """Test _processTableInfo for tournament with HIVETABLE."""
        info = {"TABLE": "Tournament Table 123", "TOURNO": "987654321", "HIVETABLE": "Hive Table 456"}

        self.parser._processTableInfo(info, self.mock_hand)
        self.assertEqual(self.mock_hand.tablename, "Hive Table 456")

    def test_process_table_info_tournament_without_hivetable(self) -> None:
        """Test _processTableInfo for tournament without HIVETABLE."""
        self.mock_hand.tourNo = "987654321"
        info = {"TABLE": "Tournament Table 123", "TOURNO": "987654321", "HIVETABLE": None}

        self.parser._processTableInfo(info, self.mock_hand)
        self.assertEqual(self.mock_hand.tablename, "Table")  # Second part after split

    def test_process_table_info_cash_game(self) -> None:
        """Test _processTableInfo for cash game."""
        info = {"TABLE": "Badugi II", "TOURNO": None, "HIVETABLE": None}

        self.parser._processTableInfo(info, self.mock_hand)
        self.assertEqual(self.mock_hand.tablename, "Badugi II")


class TestProcessHandInfoKeyIntegration(unittest.TestCase):
    """Integration tests for _processHandInfoKey with multiple keys."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.config = MockConfig()
        self.parser = PokerStars(self.config)
        self.mock_hand = Mock()
        self.mock_hand.handid = None
        self.mock_hand.tourNo = None
        self.mock_hand.level = None
        self.mock_hand.isShootout = False
        self.mock_hand.buttonpos = None
        self.mock_hand.maxseats = None
        self.mock_hand.tablename = None

    def test_process_all_basic_fields(self) -> None:
        """Test processing all basic hand fields together."""
        info = {"HID": "123456789", "DATETIME": "2024/01/01 12:00:00 ET", "TOURNO": "987654321123456789"}

        with patch.object(self.parser, "_processDateTime"):
            for key in info:
                self.parser._processHandInfoKey(key, info, self.mock_hand)

        self.assertEqual(self.mock_hand.handid, "123456789")
        self.assertEqual(self.mock_hand.tourNo, "987654321123456789")  # All 18 chars

    def test_process_all_tournament_fields(self) -> None:
        """Test processing all tournament fields together."""
        self.mock_hand.tourNo = "123456789"  # Set for BUYIN processing
        info = {"BUYIN": "$5.50+$0.50", "LEVEL": "II", "SHOOTOUT": True}

        with patch.object(self.parser, "_processBuyinInfo"):
            for key in info:
                self.parser._processHandInfoKey(key, info, self.mock_hand)

        self.assertEqual(self.mock_hand.level, "II")
        self.assertTrue(self.mock_hand.isShootout)

    def test_process_all_table_fields(self) -> None:
        """Test processing all table fields together."""
        info = {"TABLE": "Test Table", "BUTTON": 1, "MAX": "6"}

        with patch.object(self.parser, "_processTableInfo"):
            for key in info:
                self.parser._processHandInfoKey(key, info, self.mock_hand)

        self.assertEqual(self.mock_hand.buttonpos, 1)
        self.assertEqual(self.mock_hand.maxseats, 6)

    def test_process_mixed_keys_integration(self) -> None:
        """Test processing keys from different categories together."""
        info = {"HID": "123456789", "LEVEL": "III", "BUTTON": 2, "TOURNO": "987654321111111111", "MAX": "9"}

        for key in info:
            self.parser._processHandInfoKey(key, info, self.mock_hand)

        self.assertEqual(self.mock_hand.handid, "123456789")
        self.assertEqual(self.mock_hand.tourNo, "987654321111111111")  # All 18 chars
        self.assertEqual(self.mock_hand.level, "III")
        self.assertEqual(self.mock_hand.buttonpos, 2)
        self.assertEqual(self.mock_hand.maxseats, 9)


if __name__ == "__main__":
    unittest.main()
